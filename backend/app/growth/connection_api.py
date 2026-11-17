from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from app.growth import connections
from app.growth.contracts import ConnectionInput
from app.growth.models import Integration
from app.growth.runtime import record


def install_connections(app, settings, db, identity, require):
    router = APIRouter(prefix="/v1/connections")

    async def lookup(session, org_id, provider):
        item = await session.scalar(
            select(Integration).where(
                Integration.organization_id == org_id, Integration.provider == provider
            )
        )
        if not item:
            raise HTTPException(404, "not_found")
        return item

    async def audit(session, who, request, action, subject):
        await record(
            session,
            who["organization"].id,
            who["user"].id,
            action,
            subject,
            trace=request.state.trace_id,
        )

    @router.get("")
    async def listing(who=Depends(identity), session=Depends(db)):
        result = (
            await session.scalars(
                select(Integration).where(Integration.organization_id == who["organization"].id)
            )
        ).all()
        return [connections.public_connection(item) for item in result]

    @router.put("/{provider}")
    async def save(
        provider: str,
        data: ConnectionInput,
        request: Request,
        who=Depends(identity),
        session=Depends(db),
    ):
        await require(session, request, who, {"owner"})
        if provider not in connections.PROVIDERS:
            raise HTTPException(404, "unknown_provider")
        if not set(data.credentials) <= connections.FIELDS[provider]:
            raise HTTPException(422, "unknown_credential_fields")
        item = await session.scalar(
            select(Integration).where(
                Integration.organization_id == who["organization"].id,
                Integration.provider == provider,
            )
        )
        ciphertext = connections.seal(settings, provider, who["organization"].id, data.credentials)
        if not item:
            item = Integration(
                organization_id=who["organization"].id,
                provider=provider,
                account_ref=data.account_ref,
                token_ciphertext=ciphertext,
            )
            session.add(item)
        else:
            item.version += 1
            item.account_ref, item.token_ciphertext = data.account_ref, ciphertext
        item.enabled = False
        item.sync_enabled = False
        item.status = (
            "placeholder" if connections.is_placeholder(data.credentials) else "configured"
        )
        await session.flush()
        await audit(session, who, request, "connection.saved", item.id)
        await session.commit()
        return connections.public_connection(item)

    @router.post("/{provider}/verify")
    async def verify(provider: str, request: Request, who=Depends(identity), session=Depends(db)):
        await require(session, request, who, {"owner"})
        item = await lookup(session, who["organization"].id, provider)
        version = item.version
        snapshot = SimpleNamespace(
            provider=item.provider,
            organization_id=item.organization_id,
            account_ref=item.account_ref,
            token_ciphertext=item.token_ciphertext,
        )
        await session.commit()
        result = await connections.verify(settings, snapshot)
        await require(session, request, who, {"owner"})
        await session.refresh(item)
        if item.version != version or item.status == "revoked":
            raise HTTPException(409, "connection_changed_during_verification")
        item.token_ciphertext = snapshot.token_ciphertext
        item.status, item.account_ref = result["status"], result["account_ref"]
        await audit(session, who, request, "connection.verified", item.id)
        await session.commit()
        return connections.public_connection(item)

    @router.post("/{provider}/activate")
    async def activate(provider: str, request: Request, who=Depends(identity), session=Depends(db)):
        await require(session, request, who, {"owner"})
        item = await lookup(session, who["organization"].id, provider)
        if item.status != "verified":
            raise HTTPException(409, "verified_credentials_required")
        if connections.is_placeholder(connections.unseal(settings, item)):
            raise HTTPException(409, "placeholder_credentials_cannot_activate")
        item.enabled = True
        await audit(session, who, request, "connection.activated", item.id)
        await session.commit()
        return connections.public_connection(item)

    @router.post("/{provider}/disconnect")
    async def disconnect(
        provider: str, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await require(session, request, who, {"owner"}, writes=False)
        item = await lookup(session, who["organization"].id, provider)
        item.enabled, item.status, item.token_ciphertext = False, "revoked", ""
        item.sync_enabled = False
        item.version += 1
        await audit(session, who, request, "connection.disconnected", item.id)
        await session.commit()
        return connections.public_connection(item)

    app.include_router(router)
