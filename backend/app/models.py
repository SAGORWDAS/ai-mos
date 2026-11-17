"""Foundation schema. SQLite is for local development, not a production isolation boundary."""

import time
from uuid import uuid4

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Row:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Organization(Row, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(120))
    emergency_stop: Mapped[bool] = mapped_column(Boolean, default=False)


class User(Row, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(256))
    recovery_hash: Mapped[str] = mapped_column(String(64), default="")
    totp_secret: Mapped[str] = mapped_column(String(2000), default="")
    totp_pending: Mapped[str] = mapped_column(String(2000), default="")
    totp_last_counter: Mapped[float] = mapped_column(Float, default=-1)


class Tenant:
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)


class Membership(Row, Tenant, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(16))


class Session(Row, Tenant, Base):
    __tablename__ = "sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[float] = mapped_column(Float)


class Invitation(Row, Tenant, Base):
    __tablename__ = "invitations"
    email: Mapped[str] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[float] = mapped_column(Float)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)


class Brand(Row, Tenant, Base):
    __tablename__ = "brands"
    __table_args__ = (UniqueConstraint("organization_id", "name"),)
    name: Mapped[str] = mapped_column(String(120))
    website: Mapped[str] = mapped_column(String(500), default="")
    positioning: Mapped[str] = mapped_column(String(5000), default="")
    icp: Mapped[dict] = mapped_column(JSON, default=dict)
    voice: Mapped[dict] = mapped_column(JSON, default=dict)
    pricing: Mapped[dict] = mapped_column(JSON, default=dict)
    approved_claims: Mapped[list] = mapped_column(JSON, default=list)
    prohibited_claims: Mapped[list] = mapped_column(JSON, default=list)


class AuditLog(Row, Tenant, Base):
    __tablename__ = "audit_logs"
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    subject_id: Mapped[str] = mapped_column(String(36), default="")
    decision: Mapped[str] = mapped_column(String(120), default="allowed")
    trace_id: Mapped[str] = mapped_column(String(36))


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    counter: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[float] = mapped_column(Float, index=True)
