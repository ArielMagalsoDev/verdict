from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, EmailStr, Field


class LeadIn(BaseModel):
    submission_id: UUID = Field(default_factory=uuid4)
    source: Literal["website", "event", "referral", "partner"] = "website"
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    work_email: EmailStr
    company_name: str = Field(min_length=2, max_length=160)
    website: str | None = None
    job_title: str | None = None
    country: str | None = None
    message: str = Field(min_length=10, max_length=2000)
    consent_to_contact: bool
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Fact(BaseModel):
    field: Literal["industry", "employee_range", "headquarters", "locations", "technology", "business_model"]
    value: str | None
    quote: str | None
    source_url: str | None
    confidence: float = Field(ge=0, le=1)
    status: Literal["verified", "uncertain", "conflicting", "unknown"]


class Classification(BaseModel):
    category: Literal[
        "sales_inquiry",
        "vendor_solicitation",
        "job_application",
        "student_research",
        "consumer_individual",
        "unclear",
    ]
    stated_use_case: str | None = None
    reason: str


class LeadAccepted(BaseModel):
    lead_id: UUID
    job_id: UUID
    status: str = "queued"
    status_url: str
