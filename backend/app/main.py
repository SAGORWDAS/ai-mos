import asyncio
import logging
import secrets
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import event, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.accounts import check_otp, install_accounts
from app.body_limit import RequestBodyLimit
from app.config import Settings, get_settings
from app.contracts import AcceptInvite, BrandInput, Invite, Login, Signup, Stop
from app.growth.api import install
from app.growth.autopilot import install_autopilot
from app.growth.billing_api import install_billing
from app.growth.connection_api import install_connections
from app.growth.contact_api import install_contacts
from app.growth.costs import install_costs
from app.growth.discovery import install_discovery
from app.growth.embeddings import install_embeddings
from app.growth.esp_api import install_esp
from app.growth.inbox_schedule import install_inbox_schedule
from app.growth.knowledge_api import install_knowledge
from app.growth.models import (
    Approval,
    Campaign,
    Content,
    Draft,
    Effect,
    Integration,
    Lead,
    ModelUsage,
)
from app.growth.oauth import install_oauth
from app.growth.provider_api import install_provider_routes
from app.growth.publication import install_publication
from app.growth.runtime import Runtime
from app.models import AuditLog, Base, Brand, Invitation, Membership, Organization, Session, User
from app.schema import upgrade_local
from app.security import hash_password, token_hash, verify_password
from app.tenancy import tenant_scope
from app.throttling import AuthLimiter

logger = logging.getLogger("ai_mos")
COOKIE = "ai_mos_session"


def create_app(settings: Settings | None = None):
    settings = settings or get_settings()
    if settings.app_env not in ("development", "test"):
        raise RuntimeError(
            "Production is gated on managed identity, HTTPS, live provider drills "
            "and deployment review"
        )
    engine = create_async_engine(settings.database_url, pool_pre_ping=True, hide_parameters=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    worker_engine = (
        create_async_engine(settings.worker_database_url, pool_pre_ping=True, hide_parameters=True)
        if settings.worker_database_url
        else None
    )
    worker_factory = (
        async_sessionmaker(worker_engine, expire_on_commit=False) if worker_engine else factory
    )
    runtime = Runtime(worker_factory, settings)
    local = settings.database_url.startswith("sqlite")
    if local:

        @event.listens_for(engine.sync_engine, "connect")
        def sqlite_constraints(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    @asynccontextmanager
    async def lifespan(app):
        async with engine.begin() as conn:
            await conn.run_sync(upgrade_local)
            await conn.run_sync(Base.metadata.create_all)
        worker = asyncio.create_task(runtime.loop()) if settings.worker_enabled else None
        try:
            yield
        finally:
            if worker:
                worker.cancel()
                try:
                    await worker
                except asyncio.CancelledError:
                    pass
            await engine.dispose()
            if worker_engine:
                await worker_engine.dispose()

    app = FastAPI(title="AI-MOS", version="0.5.1", lifespan=lifespan)
    app.state.runtime = runtime
    app.state.factory = factory
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type", "Authorization", "X-Workspace-ID", "X-User-ID"],
    )
    auth_limiter = AuthLimiter(
        factory, settings.token_encryption_key or "local-development-throttle"
    )

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        request.state.trace_id = str(uuid4())
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin and origin not in settings.allowed_origins:
                return JSONResponse({"detail": "untrusted_origin"}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "cross_site_request"}, status_code=403)
        if (
            request.url.path.startswith("/v1/auth/")
            and request.url.path != "/v1/auth/logout"
            and request.method == "POST"
        ):
            address = request.client.host if request.client else "unknown"
            try:
                allowed = await auth_limiter.allow(address)
            except Exception:
                logger.exception("Authentication limiter unavailable")
                return JSONResponse({"detail": "authentication_temporarily_unavailable"}, 503)
            if not allowed:
                return JSONResponse(
                    {"detail": "rate_limited"}, status_code=429, headers={"Retry-After": "60"}
                )
        response = await call_next(request)
        response.headers["X-Trace-ID"] = request.state.trace_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Content-Security-Policy", "frame-ancestors 'none'; object-src 'none'; base-uri 'none'"
        )
        return response

    async def db():
        async with factory() as session:
            yield session

    async def identity(request: Request, session=Depends(db)):
        bearer = request.headers.get("authorization", "")
        token = bearer[7:] if bearer.startswith("Bearer ") else request.cookies.get(COOKIE)
        if not token:
            raise HTTPException(401, "unauthenticated")
        await tenant_scope(session, session_hash=token_hash(token))
        current = await session.scalar(
            select(Session).where(
                Session.token_hash == token_hash(token), Session.expires_at > time.time()
            )
        )
        if not current:
            raise HTTPException(401, "unauthenticated")
        expected_org = request.headers.get("x-workspace-id")
        expected_user = request.headers.get("x-user-id")
        if (expected_org and expected_org != current.organization_id) or (
            expected_user and expected_user != current.user_id
        ):
            raise HTTPException(409, "session_context_changed")
        await tenant_scope(session, current.organization_id, current.user_id)
        member = await session.scalar(
            select(Membership).where(
                Membership.user_id == current.user_id,
                Membership.organization_id == current.organization_id,
            )
        )
        if not member:
            raise HTTPException(401, "membership_revoked")
        user = await session.get(User, current.user_id)
        org = await session.get(Organization, current.organization_id)
        return {"user": user, "organization": org, "role": member.role, "session": current}

    def public_identity(who):
        return {
            "user": {"id": who["user"].id, "name": who["user"].name, "email": who["user"].email},
            "organization": {
                "id": who["organization"].id,
                "name": who["organization"].name,
                "emergency_stop": who["organization"].emergency_stop,
            },
            "role": who["role"],
        }

    async def audit(session, request, who, action, subject="", decision="allowed"):
        session.add(
            AuditLog(
                organization_id=who["organization"].id,
                actor_id=who["user"].id,
                action=action,
                subject_id=subject,
                decision=decision,
                trace_id=request.state.trace_id,
            )
        )
        logger.info(
            "org=%s actor=%s action=%s decision=%s trace=%s task=- agent=-",
            who["organization"].id,
            who["user"].id,
            action,
            decision,
            request.state.trace_id,
        )

    async def require(session, request, who, roles, writes=True):
        if who["role"] not in roles:
            await audit(session, request, who, "action.refused", decision="forbidden_role")
            await session.commit()
            raise HTTPException(403, "forbidden_role")
        stopped = False
        if writes or request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            await session.execute(
                update(Organization)
                .where(Organization.id == who["organization"].id)
                .values(emergency_stop=Organization.emergency_stop)
            )
            stopped = writes and await session.scalar(
                select(Organization.emergency_stop).where(Organization.id == who["organization"].id)
            )
            current_role = await session.scalar(
                select(Membership.role).where(
                    Membership.organization_id == who["organization"].id,
                    Membership.user_id == who["user"].id,
                )
            )
            if current_role not in roles:
                await audit(session, request, who, "action.refused", decision="membership_changed")
                await session.commit()
                raise HTTPException(403, "membership_changed")
        if stopped:
            await audit(session, request, who, "action.refused", decision="emergency_stop")
            await session.commit()
            raise HTTPException(423, "emergency_stop")

    async def issue_session(session, response, user_id, org_id):
        token = secrets.token_urlsafe(32)
        await tenant_scope(session, org_id, user_id)
        session.add(
            Session(
                user_id=user_id,
                organization_id=org_id,
                token_hash=token_hash(token),
                expires_at=time.time() + settings.session_hours * 3600,
            )
        )
        response.set_cookie(
            COOKIE,
            token,
            httponly=True,
            samesite="strict",
            secure=settings.secure_cookies,
            max_age=settings.session_hours * 3600,
            path="/",
        )

    @app.get("/healthz")
    async def healthz(session=Depends(db)):
        try:
            await session.execute(text("select 1"))
        except Exception:
            logger.exception("Database health check failed")
            return JSONResponse({"status": "degraded", "checks": {"database": False}}, 503)
        return {
            "status": "ok",
            "checks": {"database": True},
            "mode": "local" if local else "development",
            "redis_required": False,
        }

    @app.post("/v1/auth/signup", status_code=201)
    async def signup(data: Signup, request: Request, response: Response, session=Depends(db)):
        password = await asyncio.to_thread(hash_password, data.password)
        user = User(email=data.email, name=data.name.strip(), password_hash=password)
        org = Organization(name=data.organization_name.strip())
        session.add_all([user, org])
        try:
            await session.flush()
            await tenant_scope(session, org.id, user.id)
            session.add(Membership(user_id=user.id, organization_id=org.id, role="owner"))
            await issue_session(session, response, user.id, org.id)
            who = {"user": user, "organization": org, "role": "owner"}
            await audit(session, request, who, "org.created", org.id)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(409, "account_already_exists") from None
        return public_identity(who)

    @app.post("/v1/auth/login")
    async def login(data: Login, response: Response, session=Depends(db)):
        user = await session.scalar(select(User).where(User.email == data.email))
        stored = user.password_hash if user else dummy_password
        valid = await asyncio.to_thread(verify_password, data.password, stored)
        if not user or not valid:
            raise HTTPException(401, "invalid_credentials")
        claimed = await session.execute(
            update(User)
            .where(User.id == user.id, User.password_hash == stored)
            .values(password_hash=User.password_hash)
        )
        if not claimed.rowcount:
            raise HTTPException(401, "credentials_changed_sign_in_again")
        await session.refresh(user)
        await check_otp(session, settings, user, data.otp)
        await tenant_scope(session, user_id=user.id)
        member = await session.scalar(
            select(Membership).where(Membership.user_id == user.id).order_by(Membership.created_at)
        )
        if not member:
            raise HTTPException(401, "no_workspace_membership")
        await issue_session(session, response, user.id, member.organization_id)
        await session.commit()
        return {"status": "authenticated"}

    @app.get("/v1/auth/me")
    async def me(who=Depends(identity)):
        return public_identity(who)

    @app.post("/v1/auth/logout", status_code=204)
    async def logout(response: Response, who=Depends(identity), session=Depends(db)):
        await session.delete(who["session"])
        await session.commit()
        response.delete_cookie(COOKIE, path="/")

    @app.get("/v1/orgs")
    async def orgs(who=Depends(identity), session=Depends(db)):
        rows = (
            await session.execute(
                select(Organization, Membership.role)
                .join(Membership, Membership.organization_id == Organization.id)
                .where(Membership.user_id == who["user"].id)
            )
        ).all()
        return [{"id": org.id, "name": org.name, "role": role} for org, role in rows]

    @app.post("/v1/orgs/{org_id}/switch")
    async def switch(org_id: str, who=Depends(identity), session=Depends(db)):
        member = await session.scalar(
            select(Membership).where(
                Membership.organization_id == org_id, Membership.user_id == who["user"].id
            )
        )
        if not member:
            raise HTTPException(404, "not_found")
        who["session"].organization_id = org_id
        await tenant_scope(session, org_id, who["user"].id)
        await session.commit()
        return {"status": "switched"}

    @app.post("/v1/org/invitations", status_code=201)
    async def invite(data: Invite, request: Request, who=Depends(identity), session=Depends(db)):
        await require(session, request, who, {"owner", "admin"})
        if who["role"] == "admin" and data.role == "admin":
            raise HTTPException(403, "owner_required")
        token = secrets.token_urlsafe(32)
        item = Invitation(
            email=data.email,
            role=data.role,
            organization_id=who["organization"].id,
            token_hash=token_hash(token),
            expires_at=time.time() + 86400,
        )
        session.add(item)
        await session.flush()
        await audit(session, request, who, "member.invited", item.id)
        await session.commit()
        return {"token": token, "expires_in_hours": 24, "delivery": "manual"}

    @app.post("/v1/org/invitations/accept")
    async def accept(
        data: AcceptInvite, request: Request, who=Depends(identity), session=Depends(db)
    ):
        item = await session.scalar(
            select(Invitation).where(
                Invitation.token_hash == token_hash(data.token),
                Invitation.email == who["user"].email,
            )
        )
        if not item:
            raise HTTPException(404, "not_found")
        result = await session.execute(
            update(Invitation)
            .where(
                Invitation.id == item.id,
                Invitation.accepted.is_(False),
                Invitation.expires_at > time.time(),
            )
            .values(accepted=True)
        )
        if not result.rowcount:
            raise HTTPException(409, "invitation_expired_or_used")
        existing = await session.scalar(
            select(Membership).where(
                Membership.user_id == who["user"].id,
                Membership.organization_id == item.organization_id,
            )
        )
        if existing:
            await session.rollback()
            raise HTTPException(409, "already_a_member")
        session.add(
            Membership(user_id=who["user"].id, organization_id=item.organization_id, role=item.role)
        )
        who["session"].organization_id = item.organization_id
        await tenant_scope(session, item.organization_id, who["user"].id)
        who["organization"] = await session.get(Organization, item.organization_id)
        await audit(session, request, who, "member.joined", item.id)
        await session.commit()
        return {"status": "accepted"}

    @app.get("/v1/org/members")
    async def members(who=Depends(identity), session=Depends(db)):
        rows = (
            await session.execute(
                select(User, Membership.role)
                .join(Membership, Membership.user_id == User.id)
                .where(Membership.organization_id == who["organization"].id)
            )
        ).all()
        return [
            {"id": user.id, "name": user.name, "email": user.email, "role": role}
            for user, role in rows
        ]

    @app.post("/v1/org/emergency-stop")
    async def stop(data: Stop, request: Request, who=Depends(identity), session=Depends(db)):
        await require(session, request, who, {"owner"}, writes=False)
        who["organization"].emergency_stop = data.enabled
        await audit(session, request, who, "emergency_stop.set", who["organization"].id)
        await session.commit()
        return {"enabled": data.enabled}

    def brand_dict(brand):
        return {col.name: getattr(brand, col.name) for col in Brand.__table__.columns}

    async def find_brand(session, who, brand_id):
        brand = await session.scalar(
            select(Brand).where(
                Brand.id == brand_id, Brand.organization_id == who["organization"].id
            )
        )
        if not brand:
            raise HTTPException(404, "not_found")
        return brand

    @app.get("/v1/brands")
    async def brands(who=Depends(identity), session=Depends(db)):
        rows = await session.scalars(
            select(Brand)
            .where(Brand.organization_id == who["organization"].id)
            .order_by(Brand.created_at)
        )
        return [brand_dict(row) for row in rows]

    @app.get("/v1/brands/{brand_id}")
    async def get_brand(brand_id: str, who=Depends(identity), session=Depends(db)):
        return brand_dict(await find_brand(session, who, brand_id))

    async def save_brand(data, request, who, session, brand_id=None):
        await require(session, request, who, {"owner", "admin", "member"})
        if brand_id:
            brand = await find_brand(session, who, brand_id)
            changed = any(
                getattr(brand, field) != value for field, value in data.model_dump().items()
            )
            for key, value in data.model_dump().items():
                setattr(brand, key, value)
            if changed:
                org_id = who["organization"].id
                content_ids = select(Content.id).where(
                    Content.organization_id == org_id, Content.brand_id == brand.id
                )
                draft_ids = (
                    select(Draft.id)
                    .join(Lead, Draft.lead_id == Lead.id)
                    .where(
                        Draft.organization_id == org_id,
                        Lead.organization_id == org_id,
                        Lead.brand_id == brand.id,
                    )
                )
                campaign_ids = select(Campaign.id).where(
                    Campaign.organization_id == org_id, Campaign.brand_id == brand.id
                )
                await session.execute(
                    update(Approval)
                    .where(
                        Approval.organization_id == org_id,
                        Approval.status.in_(["pending", "approved"]),
                        (
                            (Approval.subject_type == "content")
                            & Approval.subject_id.in_(content_ids)
                        )
                        | ((Approval.subject_type == "draft") & Approval.subject_id.in_(draft_ids))
                        | (
                            (Approval.subject_type == "campaign")
                            & Approval.subject_id.in_(campaign_ids)
                        ),
                    )
                    .values(status="invalidated")
                )
                await session.execute(
                    update(Content)
                    .where(
                        Content.organization_id == org_id,
                        Content.brand_id == brand.id,
                        Content.status == "published_local",
                    )
                    .values(status="draft")
                )
                await audit(session, request, who, "brand.review_reset", brand.id)
        else:
            brand = Brand(organization_id=who["organization"].id, **data.model_dump())
            session.add(brand)
        try:
            await session.flush()
            await audit(
                session, request, who, "brand.updated" if brand_id else "brand.created", brand.id
            )
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(409, "brand_name_already_exists") from None
        return brand_dict(brand)

    @app.post("/v1/brands", status_code=201)
    async def create_brand(
        data: BrandInput, request: Request, who=Depends(identity), session=Depends(db)
    ):
        return await save_brand(data, request, who, session)

    @app.put("/v1/brands/{brand_id}")
    async def edit_brand(
        brand_id: str,
        data: BrandInput,
        request: Request,
        who=Depends(identity),
        session=Depends(db),
    ):
        return await save_brand(data, request, who, session, brand_id)

    @app.post("/v1/brands/{brand_id}/review")
    async def review(brand_id: str, who=Depends(identity), session=Depends(db)):
        brand = await find_brand(session, who, brand_id)
        checks = {
            "positioning": bool(brand.positioning.strip()),
            "icp.segments": bool(brand.icp.get("segments")),
            "approved_claims": bool(brand.approved_claims),
            "website": bool(brand.website),
            "voice.tone": bool(brand.voice.get("tone")),
        }
        missing = [key for key, passed in checks.items() if not passed]
        return {
            "status": "needs_information" if missing else "ready_for_drafting",
            "missing_fields": missing,
            "checks": checks,
            "method": "deterministic_field_check",
            "model_called": False,
        }

    @app.get("/v1/audit")
    async def logs(before: float | None = None, who=Depends(identity), session=Depends(db)):
        query = select(AuditLog).where(AuditLog.organization_id == who["organization"].id)
        if before is not None:
            query = query.where(AuditLog.created_at < before)
        rows = await session.scalars(query.order_by(AuditLog.created_at.desc()).limit(100))
        return [
            {col.name: getattr(row, col.name) for col in AuditLog.__table__.columns} for row in rows
        ]

    @app.get("/v1/metrics/overview")
    async def overview(who=Depends(identity), session=Depends(db)):
        count = await session.scalar(
            select(func.count())
            .select_from(Brand)
            .where(Brand.organization_id == who["organization"].id)
        )
        events = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.organization_id == who["organization"].id)
        )
        attempts, cost = (
            await session.execute(
                select(
                    func.count(ModelUsage.id), func.coalesce(func.sum(ModelUsage.cost_micros), 0)
                ).where(ModelUsage.organization_id == who["organization"].id)
            )
        ).one()
        effects = await session.scalar(
            select(func.count())
            .select_from(Effect)
            .where(
                Effect.organization_id == who["organization"].id,
                Effect.status.in_(["succeeded", "simulated"]),
            )
        )
        return {
            "brands": count,
            "audit_events": events,
            "model_calls": attempts,
            "external_effects": effects,
            "cost_minor": cost / 10000,
            "currency": "USD",
        }

    @app.get("/v1/workspace")
    async def workspace(who=Depends(identity), session=Depends(db)):
        # One identity and tenant scope for the entire initial browser snapshot.
        connections = (
            await session.scalars(
                select(Integration).where(Integration.organization_id == who["organization"].id)
            )
        ).all()
        return {
            "identity": public_identity(who),
            "brands": await brands(who=who, session=session),
            "logs": await logs(before=None, who=who, session=session),
            "members": await members(who=who, session=session),
            "orgs": await orgs(who=who, session=session),
            "metrics": await overview(who=who, session=session),
            "connections": [
                {"provider": row.provider, "enabled": row.enabled, "status": row.status}
                for row in connections
            ],
        }

    @app.get("/v1/integrations")
    async def integrations(who=Depends(identity)):
        return {
            "external_effects_enabled": False,
            "mode": settings.provider_mode,
            "providers": [
                {
                    "name": name,
                    "status": "sandbox" if settings.provider_mode == "sandbox" else "not_connected",
                }
                for name in ["OpenRouter", "Email", "Calendar", "Payments", "Prospect data"]
            ],
        }

    install_accounts(app, settings, db, identity, require)
    install_knowledge(app, db, identity, require)
    install_publication(
        app,
        db,
        identity,
        require,
        AuthLimiter(factory, settings.token_encryption_key or "local-public-limiter", limit=10),
        settings,
    )
    install_billing(app, db, identity, require)
    install_costs(app, runtime, settings, db, identity, require)
    install_contacts(app, db, identity, require)
    install_discovery(app, runtime, db, identity, require)
    install_esp(app, settings, db)
    install_oauth(app, runtime, settings, db, identity, require)
    install_inbox_schedule(app, db, identity, require)
    install_embeddings(app, runtime, settings, db, identity, require)
    install(app, runtime, settings, db, identity, require)
    install_connections(app, settings, db, identity, require)
    install_autopilot(app, runtime, settings, db, identity, require)
    install_provider_routes(app, runtime, settings, db, identity, require)
    dummy_password = hash_password(secrets.token_urlsafe(32))
    app.add_middleware(RequestBodyLimit)
    return app


app = create_app()
