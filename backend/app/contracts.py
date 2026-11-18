import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EmailInput(Input):
    email: str = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        value = value.lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address")
        return value


class Login(EmailInput):
    password: str = Field(min_length=1, max_length=256)
    otp: str = Field(default="", max_length=16)

    @field_validator("password", mode="before")
    @classmethod
    def preserve_password(cls, value):
        return value

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class Signup(Login):
    access_code: str = Field(default="", max_length=256, repr=False)
    name: str = Field(min_length=1, max_length=120)
    organization_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=256)

    @field_validator("name", "organization_name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Name cannot be blank")
        return value.strip()


class Invite(EmailInput):
    role: Literal["admin", "member", "viewer"]


class AcceptInvite(Input):
    token: str = Field(min_length=20, max_length=200)


class Stop(Input):
    enabled: bool


class ICPInput(BaseModel):
    model_config = ConfigDict(extra="allow")
    segments: list[str] = Field(default_factory=list, max_length=100)
    geographies: list[str] = Field(default_factory=list, max_length=100)


class VoiceInput(BaseModel):
    model_config = ConfigDict(extra="allow")
    tone: str = Field(default="", max_length=500)
    banned_phrases: list[str] = Field(default_factory=list, max_length=100)


class PricePlan(Input):
    name: str = Field(min_length=1, max_length=120)
    price_monthly_minor: int = Field(ge=0, le=100_000_000)
    limits: str = Field(default="", max_length=1000)


class PricingInput(Input):
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")
    plans: list[PricePlan] = Field(default_factory=list, max_length=20)
    discounts_allowed: bool = False
    discount_ceiling_pct: int = Field(default=0, ge=0, le=100)


class BrandInput(Input):
    name: str = Field(min_length=1, max_length=120)
    website: str = Field(default="", max_length=500)
    positioning: str = Field(default="", max_length=5000)
    icp: ICPInput = Field(default_factory=ICPInput)
    voice: VoiceInput = Field(default_factory=VoiceInput)
    pricing: PricingInput = Field(default_factory=PricingInput)
    approved_claims: list[Annotated[str, Field(min_length=1, max_length=600)]] = Field(
        default_factory=list, max_length=100
    )
    prohibited_claims: list[Annotated[str, Field(min_length=1, max_length=600)]] = Field(
        default_factory=list, max_length=100
    )

    @field_validator("website")
    @classmethod
    def valid_website(cls, value):
        if value and not value.startswith(("https://", "http://")):
            raise ValueError("Website must start with https:// or http://")
        return value
