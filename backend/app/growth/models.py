from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, Row, Tenant


class Command(Row, Tenant, Base):
    __tablename__ = "commands"
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    raw: Mapped[str] = mapped_column(Text)
    parsed: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="confirmed")


class Plan(Row, Tenant, Base):
    __tablename__ = "plans"
    command_id: Mapped[str] = mapped_column(ForeignKey("commands.id"))
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"))
    objective: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class Task(Row, Tenant, Base):
    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key"),)
    plan_id: Mapped[str | None] = mapped_column(ForeignKey("plans.id"))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    agent_id: Mapped[str] = mapped_column(String(16))
    type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24), default="ready", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str] = mapped_column(String(120), default="")
    leased_until: Mapped[float | None] = mapped_column(Float)
    finished_at: Mapped[float | None] = mapped_column(Float)


class TaskDependency(Tenant, Base):
    __tablename__ = "task_dependencies"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), primary_key=True)
    depends_on_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), primary_key=True)


class Agent(Row, Tenant, Base):
    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("organization_id", "role_id"),)
    role_id: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class ModelUsage(Row, Tenant, Base):
    __tablename__ = "model_usage"
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    agent_id: Mapped[str] = mapped_column(String(16))
    model_id: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(40))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_micros: Mapped[int] = mapped_column(Integer, default=0)
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    reserved_micros: Mapped[int] = mapped_column(Integer, default=0)
    reservation_period: Mapped[str] = mapped_column(String(10), default="")
    provider_ref: Mapped[str] = mapped_column(String(200), default="")
    settled: Mapped[bool] = mapped_column(Boolean, default=False)
    reconciliation_evidence: Mapped[str] = mapped_column(String(1000), default="")
    cache_source_id: Mapped[str | None] = mapped_column(ForeignKey("model_usage.id"))


class ModelCache(Row, Tenant, Base):
    __tablename__ = "model_cache"
    __table_args__ = (UniqueConstraint("organization_id", "cache_key"),)
    cache_key: Mapped[str] = mapped_column(String(64))
    model_id: Mapped[str] = mapped_column(String(200))
    source_usage_id: Mapped[str] = mapped_column(ForeignKey("model_usage.id"))
    output: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[float] = mapped_column(Float)


class Budget(Row, Tenant, Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("organization_id", "period"),)
    period: Mapped[str] = mapped_column(String(7))
    limit_micros: Mapped[int] = mapped_column(Integer, default=2_000_000)
    spent_micros: Mapped[int] = mapped_column(Integer, default=0)
    reserved_micros: Mapped[int] = mapped_column(Integer, default=0)
    daily_send_cap: Mapped[int] = mapped_column(Integer, default=20)


class BrandDocument(Row, Tenant, Base):
    __tablename__ = "brand_documents"
    __table_args__ = (UniqueConstraint("organization_id", "brand_id", "checksum"),)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"))
    title: Mapped[str] = mapped_column(String(200))
    source_uri: Mapped[str] = mapped_column(String(500), default="human-entry")
    checksum: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="indexed")


class BrandChunk(Row, Tenant, Base):
    __tablename__ = "brand_chunks"
    document_id: Mapped[str] = mapped_column(ForeignKey("brand_documents.id"))
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"))
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list] = mapped_column(JSON, default=list)
    embedding_model: Mapped[str] = mapped_column(String(200), default="")


class Lead(Row, Tenant, Base):
    __tablename__ = "leads"
    __table_args__ = (UniqueConstraint("organization_id", "email"),)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"))
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254))
    company: Mapped[str] = mapped_column(String(200), default="")
    domain: Mapped[str] = mapped_column(String(250), default="")
    source: Mapped[str] = mapped_column(String(500))
    source_confidence: Mapped[int] = mapped_column(Integer, default=100)
    lawful_basis: Mapped[str] = mapped_column(String(32))
    basis_evidence: Mapped[str] = mapped_column(Text)
    score: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="discovered")
    version: Mapped[int] = mapped_column(Integer, default=1)
    personalisation: Mapped[str] = mapped_column(String(400), default="")
    personalisation_evidence: Mapped[str] = mapped_column(String(2000), default="")


class Activity(Row, Tenant, Base):
    __tablename__ = "activities"
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str] = mapped_column(Text, default="")


class Suppression(Row, Tenant, Base):
    __tablename__ = "suppressions"
    __table_args__ = (UniqueConstraint("organization_id", "address"),)
    address: Mapped[str] = mapped_column(String(254))
    reason: Mapped[str] = mapped_column(String(24))


class Draft(Row, Tenant, Base):
    __tablename__ = "outreach_drafts"
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    claims: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="draft")


class Approval(Row, Tenant, Base):
    __tablename__ = "approvals"
    subject_type: Mapped[str] = mapped_column(String(32))
    subject_id: Mapped[str] = mapped_column(String(36))
    action_class: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    expires_at: Mapped[float] = mapped_column(Float)
    decided_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[float | None] = mapped_column(Float)


class Message(Row, Tenant, Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key"),)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    draft_id: Mapped[str | None] = mapped_column(ForeignKey("outreach_drafts.id"))
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id"))
    direction: Mapped[str] = mapped_column(String(16))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24))
    provider_id: Mapped[str] = mapped_column(String(200), default="")
    classification: Mapped[dict] = mapped_column(JSON, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)


class Meeting(Row, Tenant, Base):
    __tablename__ = "meetings"
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    title: Mapped[str] = mapped_column(String(200))
    starts_at: Mapped[float] = mapped_column(Float)
    ends_at: Mapped[float] = mapped_column(Float)
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    status: Mapped[str] = mapped_column(String(24), default="proposed")
    provider_id: Mapped[str] = mapped_column(String(200), default="")


class Campaign(Row, Tenant, Base):
    __tablename__ = "campaigns"
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"))
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(24), default="draft")
    lead_ids: Mapped[list] = mapped_column(JSON, default=list)
    budget_micros: Mapped[int] = mapped_column(Integer, default=0)


class Content(Row, Tenant, Base):
    __tablename__ = "content_items"
    __table_args__ = (UniqueConstraint("organization_id", "task_id"),)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"))
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"))
    type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="draft")


class Checkout(Row, Tenant, Base):
    __tablename__ = "checkouts"
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    description: Mapped[str] = mapped_column(String(200))
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    provider_ref: Mapped[str] = mapped_column(String(200), unique=True)
    recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    url: Mapped[str] = mapped_column(String(2000), default="")
    payment_ref: Mapped[str] = mapped_column(String(200), default="")
    subscription_ref: Mapped[str] = mapped_column(String(200), default="")


class Payment(Row, Tenant, Base):
    __tablename__ = "payments"
    provider_event_id: Mapped[str] = mapped_column(String(200), unique=True)
    checkout_id: Mapped[str] = mapped_column(ForeignKey("checkouts.id"))
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(24))
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)


class Customer(Row, Tenant, Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("organization_id", "lead_id"),)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    status: Mapped[str] = mapped_column(String(24), default="active")
    onboarding: Mapped[list] = mapped_column(JSON, default=list)
    health_score: Mapped[int] = mapped_column(Integer, default=100)
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)


class SupportThread(Row, Tenant, Base):
    __tablename__ = "support_threads"
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="open")
    response: Mapped[str] = mapped_column(Text, default="")


class Workflow(Row, Tenant, Base):
    __tablename__ = "workflows"
    name: Mapped[str] = mapped_column(String(160))
    trigger: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(80))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class WorkflowRun(Row, Tenant, Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (UniqueConstraint("organization_id", "workflow_id", "event_id"),)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"))
    event_id: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(24))
    output: Mapped[dict] = mapped_column(JSON, default=dict)


class Learning(Row, Tenant, Base):
    __tablename__ = "learning_records"
    lesson: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSON)
    effect_size: Mapped[int] = mapped_column(Integer)


class Effect(Row, Tenant, Base):
    """Durable intent and receipt; uncertain live effects must be reconciled, not retried."""

    __tablename__ = "effects"
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key"),)
    action: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    approval_id: Mapped[str] = mapped_column(ForeignKey("approvals.id"), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    payload: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    dispatch_started_at: Mapped[float | None] = mapped_column(Float)


class Integration(Row, Tenant, Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("organization_id", "provider"),)
    provider: Mapped[str] = mapped_column(String(24))
    account_ref: Mapped[str] = mapped_column(String(254))
    token_ciphertext: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="configured")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_draft_replies: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_interval_minutes: Mapped[int] = mapped_column(Integer, default=10)
    sync_next_at: Mapped[float] = mapped_column(Float, default=0)
    sync_cursor: Mapped[str] = mapped_column(String(2000), default="")
    sync_last_at: Mapped[float] = mapped_column(Float, default=0)
    sync_error: Mapped[str] = mapped_column(String(120), default="")


class DailySend(Tenant, Base):
    __tablename__ = "daily_sends"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


class Notification(Row, Tenant, Base):
    __tablename__ = "notifications"
    title: Mapped[str] = mapped_column(String(200))
    subject_id: Mapped[str] = mapped_column(String(36))
    read: Mapped[bool] = mapped_column(Boolean, default=False)


class Expense(Row, Tenant, Base):
    __tablename__ = "expenses"
    category: Mapped[str] = mapped_column(String(24))
    amount_micros: Mapped[int] = mapped_column(Integer)
    evidence: Mapped[str] = mapped_column(String(1000))
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"))


class AttributionTouch(Row, Tenant, Base):
    __tablename__ = "attribution_touches"
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key"),)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"))
    channel: Mapped[str] = mapped_column(String(40))
    evidence: Mapped[str] = mapped_column(String(1000))
    occurred_at: Mapped[float] = mapped_column(Float)
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))


class Sequence(Row, Tenant, Base):
    __tablename__ = "sequences"
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"))
    name: Mapped[str] = mapped_column(String(160))
    delay_days: Mapped[int] = mapped_column(Integer)
    max_steps: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Enrollment(Row, Tenant, Base):
    __tablename__ = "sequence_enrollments"
    __table_args__ = (UniqueConstraint("organization_id", "sequence_id", "lead_id"),)
    sequence_id: Mapped[str] = mapped_column(ForeignKey("sequences.id"))
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    step: Mapped[int] = mapped_column(Integer, default=0)
    next_at: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(24), default="active")


class Subscription(Row, Tenant, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("organization_id", "checkout_id"),)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    checkout_id: Mapped[str] = mapped_column(ForeignKey("checkouts.id"))
    status: Mapped[str] = mapped_column(String(24), default="active")
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    current_period_end: Mapped[float] = mapped_column(Float)
    provider_ref: Mapped[str] = mapped_column(String(200), default="")
    last_event_at: Mapped[float] = mapped_column(Float, default=0)


class ProviderEvent(Row, Tenant, Base):
    __tablename__ = "provider_events"
    __table_args__ = (UniqueConstraint("organization_id", "provider", "event_id"),)
    provider: Mapped[str] = mapped_column(String(24))
    event_id: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(80))
    object_ref: Mapped[str] = mapped_column(String(200))
    occurred_at: Mapped[float] = mapped_column(Float)
    amount_minor: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="")
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)


RESOURCES = {
    model.__tablename__: model
    for model in [
        Command,
        Plan,
        Task,
        Agent,
        ModelUsage,
        Budget,
        BrandDocument,
        BrandChunk,
        Lead,
        Activity,
        Suppression,
        Draft,
        Approval,
        Message,
        Meeting,
        Campaign,
        Content,
        Checkout,
        Payment,
        Customer,
        SupportThread,
        Workflow,
        WorkflowRun,
        Learning,
        Effect,
        Notification,
        Expense,
        AttributionTouch,
        Sequence,
        Enrollment,
        Subscription,
        ProviderEvent,
    ]
}
