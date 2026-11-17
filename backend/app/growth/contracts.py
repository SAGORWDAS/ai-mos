from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator

from app.contracts import EmailInput, Input


class Keyed(Input):
    idempotency_key: str = Field(min_length=8, max_length=200)


class CommandInput(Keyed):
    brand_id: str
    objective: str = Field(min_length=8, max_length=500)
    goal: Literal["leads", "sales", "cac", "retention", "efficiency"] = "leads"
    audience: str = Field(default="", max_length=500)
    target: int = Field(default=10, ge=1, le=10000)
    window_days: int = Field(default=30, ge=1, le=365)


class LeadInput(EmailInput):
    brand_id: str
    name: str = Field(min_length=1, max_length=120)
    company: str = Field(default="", max_length=200)
    domain: str = Field(default="", max_length=250)
    source: str = Field(min_length=3, max_length=500)
    source_confidence: int = Field(default=100, ge=0, le=100)
    lawful_basis: Literal["consent", "legitimate_interest", "existing_customer", "not_established"]
    basis_evidence: str = Field(min_length=3, max_length=3000)


class LeadImport(Input):
    leads: list[LeadInput] = Field(min_length=1, max_length=100)


class StageInput(Input):
    status: Literal[
        "discovered",
        "enriched",
        "scored",
        "qualified",
        "disqualified",
        "contacted",
        "replied",
        "meeting_set",
        "converted",
        "dormant",
    ]
    reason: str = Field(min_length=3, max_length=1000)


class DraftInput(Keyed):
    lead_id: str


class DraftEdit(Input):
    expected_version: int = Field(ge=1)
    subject: str = Field(min_length=3, max_length=90)
    body: str = Field(min_length=30, max_length=1200)


class Decision(Input):
    decision: Literal["approved", "rejected"]


class Execute(Keyed):
    approval_id: str
    execution_mode: Literal["sandbox", "live", "local"] = "sandbox"


class Inbound(Keyed):
    lead_id: str
    subject: str = Field(default="Reply", max_length=200)
    body: str = Field(min_length=1, max_length=5000)


class SuppressInput(EmailInput):
    reason: Literal["opt_out", "complaint", "bounce", "manual", "legal"] = "manual"


class BudgetInput(Input):
    limit_micros: int = Field(ge=0, le=1_000_000_000)
    daily_send_cap: int = Field(ge=0, le=1000)


class DocumentInput(Input):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=10, max_length=30000)
    source_uri: str = Field(default="human-entry", max_length=500)


class SearchInput(Input):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=10)


class MeetingInput(Input):
    lead_id: str
    title: str = Field(min_length=3, max_length=200)
    starts_at: float
    duration_minutes: int = Field(default=30, ge=15, le=120)
    timezone: str = "UTC"

    @field_validator("timezone")
    @classmethod
    def timezone_exists(cls, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValueError("Unknown timezone") from None
        return value


class CampaignInput(Input):
    brand_id: str
    name: str = Field(min_length=3, max_length=160)
    lead_ids: list[str] = Field(min_length=1, max_length=20)
    budget_micros: int = Field(default=0, ge=0, le=1_000_000_000)


class ContentInput(Keyed):
    brand_id: str
    type: Literal["landing_page", "article", "seo", "social", "creative_brief"]
    topic: str = Field(min_length=3, max_length=200)


class CheckoutInput(Input):
    lead_id: str
    description: str = Field(min_length=3, max_length=200)
    amount_minor: int = Field(gt=0, le=100_000_000)
    currency: str = Field(pattern="^[A-Z]{3}$")
    recurring: bool = False
    execution_mode: Literal["sandbox", "live"] = "sandbox"


class SandboxPayment(Input):
    event_id: str = Field(min_length=8, max_length=200)


class OnboardingInput(Input):
    completed: list[str] = Field(max_length=10)


class SupportInput(Input):
    customer_id: str
    subject: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=3, max_length=5000)


class SupportResponse(Input):
    response: str = Field(min_length=3, max_length=5000)
    status: Literal["open", "resolved", "escalated"]


class WorkflowInput(Input):
    name: str = Field(min_length=3, max_length=160)
    trigger: Literal["lead.created", "message.received", "payment.succeeded"]
    action: Literal["score_lead", "notify_owner", "onboarding_checklist"]
    enabled: bool = True


class WorkflowEvent(Keyed):
    subject_id: str


class LearningInput(Input):
    lesson: str = Field(min_length=10, max_length=3000)
    evidence: list[str] = Field(min_length=1, max_length=20)
    effect_size: int = Field(ge=-100, le=100)


class AgentInput(Input):
    enabled: bool


class ToolInput(Input):
    agent_id: str
    args: dict = Field(default_factory=dict)


class ExpenseInput(Input):
    category: Literal["data", "sending", "human_review", "infrastructure"]
    amount_micros: int = Field(ge=0, le=1_000_000_000)
    evidence: str = Field(min_length=3, max_length=1000)
    simulated: bool = True
    campaign_id: str | None = None


class SequenceInput(Input):
    brand_id: str
    name: str = Field(min_length=3, max_length=160)
    delay_days: int = Field(ge=1, le=90)
    max_steps: int = Field(ge=1, le=5)


class EnrollInput(Input):
    lead_id: str


class CSVImport(Input):
    brand_id: str
    content: str = Field(min_length=10, max_length=50000)


class ConnectionInput(Input):
    account_ref: str = Field(min_length=1, max_length=254)
    credentials: dict[str, str]


class InboxSync(Input):
    cursor: str | None = Field(default=None, max_length=2000)


class PaymentEvent(Input):
    event_id: str = Field(min_length=1, max_length=200)
    checkout_ref: str = Field(min_length=1, max_length=200)
    type: Literal["payment.succeeded"]
    amount_minor: int = Field(strict=True, gt=0)
    currency: str = Field(pattern="^[A-Z]{3}$")
