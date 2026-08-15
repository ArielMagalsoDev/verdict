import uuid
from datetime import UTC, date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def now() -> datetime:
    return datetime.now(UTC)


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Seeded fictional CRM — identity-resolution tables (mirrors
# docs/schema-reconstructed-2026-08-08.sql from the original Next.js app).
# Text primary keys ("c1", "p1", ...) for the seeded rows; new rows created
# through the approval-gated CRM write flow get a fresh uuid4 hex string.
# ---------------------------------------------------------------------------
class CrmCompany(Base):
    __tablename__ = "crm_companies"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    domain_normalized: Mapped[str | None] = mapped_column(String(200), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CrmContact(Base):
    __tablename__ = "crm_contacts"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    email_normalized: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("crm_companies.id"))
    first_name: Mapped[str | None] = mapped_column(String(80))
    last_name: Mapped[str | None] = mapped_column(String(80))
    job_title: Mapped[str | None] = mapped_column(String(160))
    # "prospect" (created/updated by an approved change set) | "vendor" (seeded)
    contact_type: Mapped[str] = mapped_column(String(20), default="prospect")
    qualification_band: Mapped[str | None] = mapped_column(String(30))
    qualification_score: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


# ---------------------------------------------------------------------------
# Leads + pipeline state
# ---------------------------------------------------------------------------
class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    submission_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(20), default="website")
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80))
    work_email: Mapped[str] = mapped_column(String(320))
    email_normalized: Mapped[str] = mapped_column(String(320), index=True)
    company_name: Mapped[str] = mapped_column(String(160))
    website: Mapped[str | None] = mapped_column(String(200))
    job_title: Mapped[str | None] = mapped_column(String(160))
    country: Mapped[str | None] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(Text)
    consent_to_contact: Mapped[bool] = mapped_column(Boolean)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    # processing | completed | failed_permanent
    status: Mapped[str] = mapped_column(String(30), default="processing", index=True)
    scenario_key: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), index=True)
    job_type: Mapped[str] = mapped_column(String(40), default="process_lead")
    # queued | running | completed | failed_permanent
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class IdentityMatch(Base):
    __tablename__ = "identity_matches"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), unique=True, index=True)
    match_type: Mapped[str] = mapped_column(String(20))  # confident | possible | none
    matched_contact_id: Mapped[str | None] = mapped_column(ForeignKey("crm_contacts.id"))
    matched_company_id: Mapped[str | None] = mapped_column(ForeignKey("crm_companies.id"))
    candidates: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CompanyFact(Base):
    __tablename__ = "company_facts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), index=True)
    field: Mapped[str] = mapped_column(String(30))
    value: Mapped[str | None] = mapped_column(Text)
    quote: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(200))
    source_title: Mapped[str | None] = mapped_column(String(200))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20))  # verified | uncertain | conflicting | unknown
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class QualificationDecision(Base):
    __tablename__ = "qualification_decisions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), unique=True, index=True)
    score: Mapped[int | None] = mapped_column(Integer)
    band: Mapped[str] = mapped_column(String(30))
    criteria: Mapped[list] = mapped_column(JSON, default=list)
    reason: Mapped[str] = mapped_column(Text)
    missing_information: Mapped[list] = mapped_column(JSON, default=list)
    recommended_owner: Mapped[str | None] = mapped_column(String(80))
    recommended_action: Mapped[str] = mapped_column(Text)
    ruleset_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CrmChangeSet(Base):
    __tablename__ = "crm_change_sets"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), unique=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True)
    contact_action: Mapped[str] = mapped_column(String(10), default="none")  # create | update | none
    company_action: Mapped[str] = mapped_column(String(10), default="none")
    existing_contact_id: Mapped[str | None] = mapped_column(ForeignKey("crm_contacts.id"))
    existing_company_id: Mapped[str | None] = mapped_column(ForeignKey("crm_companies.id"))
    field_changes: Mapped[list] = mapped_column(JSON, default=list)
    # pending | applied | rejected — the port's own approval-gated write flow.
    status: Mapped[str] = mapped_column(String(20), default="pending")
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OutreachDraft(Base):
    __tablename__ = "outreach_drafts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), index=True)
    generated_body: Mapped[str] = mapped_column(Text)
    approved_body: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending_review")
    unsupported_claims: Mapped[list] = mapped_column(JSON, default=list)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20))  # started | completed | failed | skipped
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(Text)
    external_reference: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class AppliedChange(Base):
    __tablename__ = "applied_changes"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    change_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crm_change_sets.id"), unique=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# ---------------------------------------------------------------------------
# Abuse controls + demo infrastructure
# ---------------------------------------------------------------------------
class RateLimitEvent(Base):
    __tablename__ = "rate_limit_events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    client_key: Mapped[str] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class SpendLedger(Base):
    __tablename__ = "spend_ledger"
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    spend_usd: Mapped[float] = mapped_column(Float, default=0.0)


class ResponseCache(Base):
    __tablename__ = "response_cache"
    cache_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EvalRun(Base):
    __tablename__ = "eval_runs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    eval_set_version: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(60), default="deterministic-fallback")
    total_cases: Mapped[int] = mapped_column(Integer)
    passed_cases: Mapped[int] = mapped_column(Integer)
    accuracy: Mapped[float] = mapped_column(Float)
    false_score_count: Mapped[int] = mapped_column(Integer)
    false_refusal_count: Mapped[int] = mapped_column(Integer)
    category_breakdown: Mapped[list] = mapped_column(JSON, default=list)
    failures: Mapped[list] = mapped_column(JSON, default=list)
    mean_latency_ms: Mapped[int | None] = mapped_column(Integer)
    total_cost_usd: Mapped[float | None] = mapped_column(Float)
