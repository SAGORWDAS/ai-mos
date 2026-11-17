"""Offline recovery, RFC 6238 TOTP and owner-controlled membership lifecycle."""

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import ConfigDict, Field
from sqlalchemy import delete, select, update

from app.contracts import EmailInput, Input
from app.growth.connections import cipher
from app.growth.runtime import record
from app.models import Membership, Session, User
from app.security import hash_password, token_hash, verify_password
from app.tenancy import tenant_scope


class PasswordProof(Input):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    password: str = Field(min_length=1, max_length=256)
    otp: str = Field(default="", max_length=16)


class Recover(EmailInput):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    code: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=12, max_length=256)


class Confirm(Input):
    otp: str = Field(pattern=r"^\d{6}$")


class MemberRole(Input):
    role: str = Field(pattern="^(admin|member|viewer)$")


class Transfer(PasswordProof):
    user_id: str


def totp(secret, counter):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return f"{(struct.unpack('>I', digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1000000:06d}"


def wrap(settings, user_id, secret):
    return (
        cipher(settings)
        .encrypt(json.dumps({"user_id": user_id, "secret": secret}).encode())
        .decode()
    )


def unwrap(settings, user_id, value):
    try:
        data = json.loads(cipher(settings).decrypt(value.encode()))
        if data["user_id"] != user_id:
            raise ValueError()
        return data["secret"]
    except (InvalidToken, ValueError, KeyError):
        raise HTTPException(409, "authenticator_secret_unavailable") from None


async def check_otp(session, settings, user, code):
    if not user.totp_secret:
        return
    secret = unwrap(settings, user.id, user.totp_secret)
    now = int(time.time() // 30)
    matched = next(
        (c for c in [now - 1, now, now + 1] if hmac.compare_digest(totp(secret, c), code)), None
    )
    if matched is None:
        raise HTTPException(401, "authenticator_code_required_or_invalid")
    result = await session.execute(
        update(User)
        .where(User.id == user.id, User.totp_last_counter < matched)
        .values(totp_last_counter=matched)
    )
    if not result.rowcount:
        raise HTTPException(401, "authenticator_code_already_used")


def install_accounts(app, settings, db, identity, require):
    router = APIRouter(prefix="/v1")

    async def proof(session, who, data):
        user = who["user"]
        claimed = await session.execute(
            update(User)
            .where(User.id == user.id, User.password_hash == user.password_hash)
            .values(password_hash=User.password_hash)
        )
        if not claimed.rowcount:
            raise HTTPException(401, "credentials_changed_sign_in_again")
        await session.refresh(user)
        if not await asyncio.to_thread(verify_password, data.password, who["user"].password_hash):
            raise HTTPException(401, "invalid_credentials")
        await check_otp(session, settings, who["user"], data.otp)

    async def event(session, who, action, subject):
        await record(session, who["organization"].id, who["user"].id, action, subject)

    @router.get("/auth/security")
    async def status(who=Depends(identity)):
        return {
            "mfa_enabled": bool(who["user"].totp_secret),
            "recovery_configured": bool(who["user"].recovery_hash),
        }

    @router.post("/auth/recovery-code")
    async def recovery(data: PasswordProof, who=Depends(identity), session=Depends(db)):
        await proof(session, who, data)
        code = secrets.token_urlsafe(32)
        who["user"].recovery_hash = token_hash(code)
        await event(session, who, "security.recovery_rotated", who["user"].id)
        await session.commit()
        return {
            "code": code,
            "display": "once",
            "purpose": "Offline account recovery; store privately",
        }

    @router.post("/auth/recover")
    async def recover(data: Recover, response: Response, session=Depends(db)):
        password = await asyncio.to_thread(hash_password, data.password)
        user = await session.scalar(select(User).where(User.email == data.email))
        if (
            not user
            or not user.recovery_hash
            or not hmac.compare_digest(user.recovery_hash, token_hash(data.code))
        ):
            raise HTTPException(401, "invalid_recovery_credentials")
        claimed = await session.execute(
            update(User)
            .where(User.id == user.id, User.recovery_hash == token_hash(data.code))
            .values(
                password_hash=password,
                recovery_hash="",
                totp_secret="",
                totp_pending="",
                totp_last_counter=-1,
            )
        )
        if not claimed.rowcount:
            raise HTTPException(401, "invalid_recovery_credentials")
        await tenant_scope(session, user_id=user.id)
        await session.execute(delete(Session).where(Session.user_id == user.id))
        await session.commit()
        response.delete_cookie("ai_mos_session", path="/")
        return {"status": "recovered", "sessions_revoked": True, "mfa_reset": True}

    @router.post("/auth/mfa/setup")
    async def setup(data: PasswordProof, who=Depends(identity), session=Depends(db)):
        await proof(session, who, data)
        user = who["user"]
        if user.totp_secret:
            raise HTTPException(409, "disable_existing_authenticator_first")
        secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
        user.totp_pending = wrap(settings, user.id, secret)
        await event(session, who, "security.mfa_setup", user.id)
        await session.commit()
        return {
            "secret": secret,
            "uri": "otpauth://totp/"
            + quote("AI-MOS:" + user.email)
            + "?secret="
            + secret
            + "&issuer=AI-MOS&digits=6&period=30",
        }

    @router.post("/auth/mfa/confirm")
    async def confirm(data: Confirm, who=Depends(identity), session=Depends(db)):
        user = who["user"]
        if not user.totp_pending or user.totp_secret:
            raise HTTPException(409, "authenticator_setup_required")
        secret = unwrap(settings, user.id, user.totp_pending)
        now = int(time.time() // 30)
        matched = next(
            (c for c in [now - 1, now, now + 1] if hmac.compare_digest(totp(secret, c), data.otp)),
            None,
        )
        if matched is None:
            raise HTTPException(401, "invalid_authenticator_code")
        # Update only this setup: concurrent setup/confirm cannot install a stale secret.
        result = await session.execute(
            update(User)
            .where(
                User.id == user.id, User.totp_pending == user.totp_pending, User.totp_secret == ""
            )
            .values(totp_secret=user.totp_pending, totp_pending="", totp_last_counter=matched)
        )
        if not result.rowcount:
            raise HTTPException(409, "authenticator_setup_changed")
        await tenant_scope(session, user_id=user.id)
        await session.execute(
            delete(Session).where(Session.user_id == user.id, Session.id != who["session"].id)
        )
        await event(session, who, "security.mfa_enabled", user.id)
        await session.commit()
        return {"status": "enabled"}

    @router.post("/auth/mfa/disable")
    async def disable(data: PasswordProof, who=Depends(identity), session=Depends(db)):
        await proof(session, who, data)
        who["user"].totp_secret, who["user"].totp_pending = "", ""
        who["user"].totp_last_counter = -1
        await event(session, who, "security.mfa_disabled", who["user"].id)
        await session.commit()
        return {"status": "disabled"}

    @router.put("/org/members/{user_id}")
    async def role(
        user_id: str, data: MemberRole, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await require(session, request, who, {"owner"})
        item = await session.scalar(
            select(Membership).where(
                Membership.organization_id == who["organization"].id, Membership.user_id == user_id
            )
        )
        if not item:
            raise HTTPException(404, "not_found")
        if item.role == "owner":
            raise HTTPException(409, "use_ownership_transfer")
        item.role = data.role
        await event(session, who, "member.role_changed", user_id)
        await session.commit()
        return {"status": "updated"}

    @router.post("/org/members/{user_id}/remove")
    async def remove(user_id: str, request: Request, who=Depends(identity), session=Depends(db)):
        await require(session, request, who, {"owner"})
        item = await session.scalar(
            select(Membership).where(
                Membership.organization_id == who["organization"].id, Membership.user_id == user_id
            )
        )
        if not item:
            raise HTTPException(404, "not_found")
        if item.role == "owner":
            raise HTTPException(409, "cannot_remove_owner")
        await session.execute(
            delete(Session).where(
                Session.organization_id == item.organization_id, Session.user_id == user_id
            )
        )
        await session.delete(item)
        await event(session, who, "member.removed", user_id)
        await session.commit()
        return {"status": "removed"}

    @router.post("/org/transfer")
    async def transfer(
        data: Transfer, request: Request, who=Depends(identity), session=Depends(db)
    ):
        await require(session, request, who, {"owner"})
        await proof(session, who, data)
        org_id = who["organization"].id
        new = await session.scalar(
            select(Membership).where(
                Membership.organization_id == org_id, Membership.user_id == data.user_id
            )
        )
        if not new or new.user_id == who["user"].id:
            raise HTTPException(409, "choose_another_existing_member")
        old = await session.scalar(
            select(Membership).where(
                Membership.organization_id == org_id, Membership.user_id == who["user"].id
            )
        )
        old.role, new.role = "admin", "owner"
        await event(session, who, "organization.ownership_transferred", new.user_id)
        await session.commit()
        return {"status": "transferred"}

    app.include_router(router)
