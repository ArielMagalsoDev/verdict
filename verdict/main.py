from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from .audit import record_audit_event
from .config import settings
from .crm import apply_change_set, reject_change_set
from .db import init_db, session_scope
from .domain.changeset import derive_outcome
from .domain.validate import ValidationError, validate_lead
from .fixtures import DEMO_SCENARIOS, PROJECTS, find_mini_web_page_by_slug, find_scenario
from .limits import check_rate_limit, refund_spend, reserve_spend, verify_turnstile
from .models import (
    AppliedChange,
    AuditEvent,
    CompanyFact,
    CrmChangeSet,
    EvalRun,
    IdentityMatch,
    Job,
    Lead,
    OutreachDraft,
    QualificationDecision,
)
from .ops import (
    evaluate_alerts,
    get_band_counts,
    get_draft_status_counts,
    get_duplicate_write_prevented_count,
    get_identity_match_counts,
    get_lead_status_counts,
    get_spend_today,
    get_stage_latency,
    get_stuck_workflows,
    get_unsupported_fact_rate,
)
from .pipeline import process_lead
from .schemas import DraftDecisionIn, LeadAccepted
from .seed import seed_crm

ROOT = Path(__file__).parent
templates = Jinja2Templates(directory=ROOT / "templates")

# Schema creation + CRM seeding run at import time rather than in an ASGI
# lifespan hook: serverless ASGI adapters don't reliably invoke `lifespan`,
# but module import always runs exactly once before any request is served,
# on every platform. Both calls are
# idempotent/retry-safe (see db.init_db, seed.seed_crm) so a cold start
# racing another process is handled the same way it is in Docker Compose.
init_db()
with session_scope() as _startup_db:
    seed_crm(_startup_db)

app = FastAPI(title="Verdict", version="1.0.0")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(request: Request, exc: FastAPIHTTPException):
    """Unwraps dict details to the top level so API errors are shaped
    {"error": "...", "message": "..."} rather than FastAPI's default
    {"detail": {...}} envelope."""
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


def db_session():
    with session_scope() as db:
        yield db


def admin(x_admin_token: str = Header(default="")):
    if x_admin_token != settings().admin_token:
        raise HTTPException(401, detail={"error": "Admin token required"})


def serialize_lead(db: Session, lead: Lead) -> dict:
    identity_row = db.scalar(select(IdentityMatch).where(IdentityMatch.lead_id == lead.id))
    facts_rows = db.scalars(
        select(CompanyFact).where(CompanyFact.lead_id == lead.id).order_by(CompanyFact.created_at)
    ).all()
    decision_row = db.scalar(select(QualificationDecision).where(QualificationDecision.lead_id == lead.id))
    change_set_row = db.scalar(select(CrmChangeSet).where(CrmChangeSet.lead_id == lead.id))
    draft_row = db.scalar(
        select(OutreachDraft).where(OutreachDraft.lead_id == lead.id).order_by(OutreachDraft.created_at.desc())
    )
    events = db.scalars(
        select(AuditEvent).where(AuditEvent.lead_id == lead.id).order_by(AuditEvent.created_at)
    ).all()

    identity = (
        {
            "match_type": identity_row.match_type,
            "matched_contact_id": identity_row.matched_contact_id,
            "matched_company_id": identity_row.matched_company_id,
            "candidates": identity_row.candidates,
        }
        if identity_row
        else None
    )

    decision = (
        {
            "score": decision_row.score,
            "band": decision_row.band,
            "criteria": decision_row.criteria,
            "reason": decision_row.reason,
            "missing_information": decision_row.missing_information,
            "recommended_action": decision_row.recommended_action,
            "ruleset_version": decision_row.ruleset_version,
        }
        if decision_row
        else None
    )

    outcome = derive_outcome(identity, decision) if identity and decision else None

    return {
        "id": str(lead.id),
        "status": lead.status,
        "outcome": outcome,
        "lead": {
            "id": str(lead.id),
            "status": lead.status,
            "submission_id": lead.submission_id,
            "source": lead.source,
            "first_name": lead.first_name,
            "last_name": lead.last_name,
            "work_email": lead.work_email,
            "company_name": lead.company_name,
            "website": lead.website,
            "job_title": lead.job_title,
            "country": lead.country,
            "message": lead.message,
            "consent_to_contact": lead.consent_to_contact,
            "submitted_at": lead.submitted_at.isoformat(),
        },
        "identity": identity,
        "facts": [
            {
                "field": f.field,
                "value": f.value,
                "quote": f.quote,
                "source_url": f.source_url,
                "source_title": f.source_title,
                "confidence": f.confidence,
                "status": f.status,
            }
            for f in facts_rows
        ],
        "decision": decision,
        "change_set": None
        if not change_set_row
        else {
            "id": str(change_set_row.id),
            "status": change_set_row.status,
            "contact_action": change_set_row.contact_action,
            "company_action": change_set_row.company_action,
            "field_changes": change_set_row.field_changes,
        },
        "draft": None
        if not draft_row
        else {
            "id": str(draft_row.id),
            "generated_body": draft_row.generated_body,
            "approved_body": draft_row.approved_body,
            "status": draft_row.status,
            "unsupported_claims": draft_row.unsupported_claims,
        },
        "audit_events": [
            {
                "event_type": e.event_type,
                "status": e.status,
                "summary": e.summary,
                "duration_ms": e.duration_ms,
                "timestamp": e.created_at.isoformat(),
            }
            for e in events
        ],
    }


# ---------------------------------------------------------------------------
# HTML pages
# ---------------------------------------------------------------------------
RAMP_FG = {1: "var(--outcome-duplicate-fg)", 2: "var(--outcome-insufficient-fg)", 3: "var(--outcome-disqualified-fg)"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(db_session)):
    run = db.scalar(select(EvalRun).order_by(EvalRun.run_at.desc()))
    current_metric = (
        {"value": f"{round(run.accuracy * 100)}%", "label": f"accuracy across {run.total_cases} cases"}
        if run
        else None
    )
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "page": "home",
            "eval_run": run,
            "projects": PROJECTS,
            "current_metric": current_metric,
            "ramp_fg": RAMP_FG,
        },
    )


@app.get("/demo", response_class=HTMLResponse)
def demo(request: Request):
    return templates.TemplateResponse(
        request,
        "demo.html",
        {"page": "demo", "scenarios": DEMO_SCENARIOS, "turnstile_site_key": settings().turnstile_site_key},
    )


@app.get("/architecture", response_class=HTMLResponse)
def architecture(request: Request):
    return templates.TemplateResponse(request, "architecture.html", {"page": "architecture"})


CATEGORY_LABEL = {
    "sales_ready": "Sales-ready",
    "needs_review": "Needs review",
    "nurture": "Nurture",
    "disqualified": "Disqualified",
    "duplicate": "Duplicate / merge review",
    "insufficient_evidence": "Insufficient evidence",
    "adversarial": "Adversarial (prompt injection)",
}


@app.get("/evals", response_class=HTMLResponse)
def evals(request: Request, db: Session = Depends(db_session)):
    run = db.scalar(select(EvalRun).order_by(EvalRun.run_at.desc()))
    return templates.TemplateResponse(
        request, "evals.html", {"page": "evals", "run": run, "category_label": CATEGORY_LABEL}
    )


@app.get("/operations", response_class=HTMLResponse)
def operations(request: Request, db: Session = Depends(db_session)):
    lead_status_counts = get_lead_status_counts(db)
    band_counts = get_band_counts(db)
    identity_counts = get_identity_match_counts(db)
    draft_counts = get_draft_status_counts(db)
    stage_latency = get_stage_latency(db)
    spend_today = get_spend_today(db)
    stuck = get_stuck_workflows(db)
    dup_prevented = get_duplicate_write_prevented_count(db)
    unsupported = get_unsupported_fact_rate(db)
    alerts = evaluate_alerts(stuck, dup_prevented, unsupported)
    total_leads = sum(lead_status_counts.values())
    completed = lead_status_counts.get("completed", 0)
    return templates.TemplateResponse(
        request,
        "operations.html",
        {
            "page": "operations",
            "lead_status_counts": lead_status_counts,
            "band_counts": band_counts,
            "identity_counts": identity_counts,
            "draft_counts": draft_counts,
            "stage_latency": stage_latency,
            "spend_today": spend_today,
            "stuck": stuck,
            "alerts": alerts,
            "total_leads": total_leads,
            "completed": completed,
            "completion_rate": None if total_leads == 0 else round((completed / total_leads) * 100),
            "estimated_cost_per_lead": settings().estimated_cost_per_lead_usd,
        },
    )


@app.get("/sources/{slug}", response_class=HTMLResponse)
def source(request: Request, slug: str):
    page = find_mini_web_page_by_slug(slug)
    if not page:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "source.html", {"page": "source", "source": page})


# ---------------------------------------------------------------------------
# API — lead intake
# ---------------------------------------------------------------------------
def _client_key(request: Request) -> str:
    return request.headers.get("x-forwarded-for") or "local-dev"


def _submit_lead(db: Session, request: Request, raw: dict, scenario_key: str | None = None) -> LeadAccepted:
    client_key = _client_key(request)
    turnstile_token = str(raw.get("turnstile_token") or "")

    # Turnstile runs first, ahead of even the idempotency lookup — applies
    # uniformly to guided-scenario clicks and raw-payload submissions alike.
    if not verify_turnstile(turnstile_token, client_key):
        raise HTTPException(
            403, detail={"error": "bot_check_failed", "message": "Couldn't verify you're human — please try again."}
        )

    payload = {k: v for k, v in raw.items() if k != "turnstile_token"}
    try:
        lead_dict, email_normalized, _website_normalized = validate_lead(payload)
    except ValidationError as exc:
        raise HTTPException(422, detail={"error": "validation_failed", "details": exc.errors}) from exc

    existing = db.scalar(select(Lead).where(Lead.submission_id == lead_dict["submission_id"]))
    # A lead that failed permanently (e.g. a transient config problem at the
    # time) is retried rather than replayed forever — process_lead() already
    # clears partial child rows on reprocessing. Retries still pass through
    # the rate-limit and spend gates below like any fresh submission.
    retrying = existing is not None and existing.status == "failed_permanent"
    if existing and not retrying:
        job = db.scalar(select(Job).where(Job.lead_id == existing.id))
        return LeadAccepted(
            lead_id=existing.id,
            job_id=job.id if job else existing.id,
            status=existing.status,
            status_url=f"/api/v1/leads/{existing.id}",
            replayed=True,
        )

    rate = check_rate_limit(db, client_key)
    if not rate["allowed"]:
        raise HTTPException(
            429, detail={"error": "rate_limited", "message": "Too many requests — try again in a few minutes."}
        )

    spend = reserve_spend(db)
    if not spend["allowed"]:
        raise HTTPException(
            503,
            detail={
                "error": "budget_exhausted",
                "message": "Daily demo budget reached. The guided scenarios still work from cache.",
            },
        )

    if retrying:
        job = db.scalar(select(Job).where(Job.lead_id == existing.id))
        if job is None:
            job = Job(lead_id=existing.id)
            db.add(job)
        existing.status = "processing"
        job.status = "queued"
        job.available_at = datetime.now(UTC)
        job.last_error = None
        db.commit()
        if settings().inline_processing:
            _process_inline(db, existing, job)
        return LeadAccepted(lead_id=existing.id, job_id=job.id, status_url=f"/api/v1/leads/{existing.id}")

    submitted_at = lead_dict["submitted_at"]
    if isinstance(submitted_at, str):
        submitted_at = datetime.fromisoformat(submitted_at.replace("Z", "+00:00"))

    lead = Lead(
        submission_id=lead_dict["submission_id"],
        source=lead_dict["source"],
        first_name=lead_dict["first_name"],
        last_name=lead_dict["last_name"],
        work_email=lead_dict["work_email"],
        email_normalized=email_normalized,
        company_name=lead_dict["company_name"],
        website=lead_dict["website"],
        job_title=lead_dict["job_title"],
        country=lead_dict["country"],
        message=lead_dict["message"],
        consent_to_contact=lead_dict["consent_to_contact"],
        submitted_at=submitted_at,
        status="processing",
        scenario_key=scenario_key,
    )
    db.add(lead)
    db.flush()
    job = Job(lead_id=lead.id)
    db.add(job)
    db.commit()

    if settings().inline_processing:
        _process_inline(db, lead, job)

    return LeadAccepted(lead_id=lead.id, job_id=job.id, status_url=f"/api/v1/leads/{lead.id}")


def _process_inline(db: Session, lead: Lead, job: Job) -> None:
    """Serverless fallback for environments with no persistent worker
    process (see Settings.inline_processing): runs the pipeline synchronously
    within the request, then marks the job accordingly, mirroring worker.py's
    own single-attempt terminal states. The response is still sent after this
    returns, so by the time a client's first poll lands the lead is already
    complete — a blocking request wrapped in the same 202/poll API shape the
    async worker path uses."""
    job.status = "running"
    job.attempts += 1
    db.commit()
    try:
        process_lead(db, lead)
        job.status = "completed"
        db.commit()
    except Exception as exc:  # noqa: BLE001 — single attempt inline, no retry queue to hand off to
        db.rollback()
        lead = db.get(Lead, lead.id)
        lead.status = "failed_permanent"
        job = db.get(Job, job.id)
        job.status = "failed_permanent"
        job.last_error = str(exc)
        db.commit()
        refund_spend(db)


@app.post("/api/v1/leads", response_model=LeadAccepted, status_code=202)
async def create_lead(request: Request, db: Session = Depends(db_session)):
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(400, detail={"error": "invalid JSON body"}) from exc
    if not isinstance(body, dict):
        raise HTTPException(400, detail={"error": "invalid JSON body"})
    return _submit_lead(db, request, body)


@app.post("/api/v1/scenarios/{key}", response_model=LeadAccepted, status_code=202)
async def scenario(key: str, request: Request, db: Session = Depends(db_session)):
    found = find_scenario(key)
    if not found:
        raise HTTPException(404, detail={"error": "unknown scenarioKey"})
    try:
        body = await request.json()
    except Exception:
        body = {}
    payload = dict(found["lead"])
    if isinstance(body, dict) and body.get("turnstile_token"):
        payload["turnstile_token"] = body["turnstile_token"]
    return _submit_lead(db, request, payload, scenario_key=found["key"])


@app.get("/api/v1/leads/{lead_id}")
def get_lead(lead_id: UUID, db: Session = Depends(db_session)):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, detail={"error": "not_found"})
    return serialize_lead(db, lead)


@app.post("/api/v1/leads/{lead_id}/draft")
def decide_draft(lead_id: UUID, decision: DraftDecisionIn, db: Session = Depends(db_session)):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, detail={"error": "not_found"})
    draft = db.scalar(
        select(OutreachDraft).where(OutreachDraft.lead_id == lead_id).order_by(OutreachDraft.created_at.desc())
    )
    if not draft:
        raise HTTPException(404, detail={"error": "no draft found for this lead"})
    if decision.action == "approve" and draft.unsupported_claims:
        raise HTTPException(409, detail={"error": "cannot approve a draft with unsupported claims"})

    if decision.action == "approve":
        draft.status = "approved"
        draft.approved_body = decision.edited_body or draft.generated_body
    else:
        draft.status = "rejected"
    draft.reviewed_at = datetime.now(UTC)
    db.commit()

    edited = decision.action == "approve" and bool(decision.edited_body)
    record_audit_event(
        db,
        lead_id,
        "draft_decision",
        "completed",
        (
            "Draft approved (simulated — nothing sent)"
            if decision.action == "approve"
            else "Draft rejected"
        )
        + (", body edited before approval" if edited else ""),
    )

    return {
        "draft": {
            "id": str(draft.id),
            "generated_body": draft.generated_body,
            "approved_body": draft.approved_body,
            "status": draft.status,
            "unsupported_claims": draft.unsupported_claims,
        }
    }


# ---------------------------------------------------------------------------
# API — approval-gated CRM writes (see verdict/crm.py)
# ---------------------------------------------------------------------------
@app.post("/api/v1/crm-change-sets/{change_id}/approve", dependencies=[Depends(admin)])
def approve(change_id: UUID, db: Session = Depends(db_session)):
    cs = db.get(CrmChangeSet, change_id)
    if not cs:
        raise HTTPException(404)
    try:
        apply_change_set(db, cs)
    except ValueError as exc:
        raise HTTPException(409, detail={"error": str(exc)}) from exc
    return {"id": str(cs.id), "status": cs.status}


@app.post("/api/v1/crm-change-sets/{change_id}/reject", dependencies=[Depends(admin)])
def reject(change_id: UUID, db: Session = Depends(db_session)):
    cs = db.get(CrmChangeSet, change_id)
    if not cs:
        raise HTTPException(404)
    try:
        reject_change_set(db, cs)
    except ValueError as exc:
        raise HTTPException(409, detail={"error": str(exc)}) from exc
    return {"id": str(cs.id), "status": cs.status}


@app.get("/api/v1/admin/leads", dependencies=[Depends(admin)])
def list_leads(status: str | None = None, db: Session = Depends(db_session)):
    """Ops hygiene: a minimal id/status/company listing so debris (e.g. a lead
    stuck failed_permanent from an unrelated config outage) can be found and
    passed to DELETE /api/v1/admin/leads/{id} without a DB console."""
    stmt = select(Lead).order_by(Lead.created_at.desc())
    if status:
        stmt = stmt.where(Lead.status == status)
    rows = db.scalars(stmt).all()
    return {
        "leads": [
            {
                "id": str(lead.id),
                "status": lead.status,
                "company_name": lead.company_name,
                "scenario_key": lead.scenario_key,
                "created_at": lead.created_at.isoformat(),
            }
            for lead in rows
        ]
    }


@app.delete("/api/v1/admin/leads/{lead_id}", dependencies=[Depends(admin)])
def delete_lead(lead_id: UUID, db: Session = Depends(db_session)):
    """Ops hygiene: hard-delete a lead and every child row it produced — for
    clearing test/incident debris (e.g. leads stuck failed_permanent from an
    unrelated config outage) out of the /operations counts. Not exposed in
    any UI; admin-token gated like the CRM approve/reject actions above."""
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404)
    change_set_ids = db.scalars(select(CrmChangeSet.id).where(CrmChangeSet.lead_id == lead_id)).all()
    if change_set_ids:
        db.query(AppliedChange).filter(AppliedChange.change_set_id.in_(change_set_ids)).delete(
            synchronize_session=False
        )
    for model in (Job, IdentityMatch, CompanyFact, QualificationDecision, CrmChangeSet, OutreachDraft, AuditEvent):
        db.query(model).filter(model.lead_id == lead_id).delete(synchronize_session=False)
    db.delete(lead)
    db.commit()
    return {"id": str(lead_id), "status": "deleted"}


# ---------------------------------------------------------------------------
# Ops
# ---------------------------------------------------------------------------
@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready(db: Session = Depends(db_session)):
    db.execute(sa_text("SELECT 1"))
    return {"status": "ready"}


@app.get("/metrics")
def metrics(db: Session = Depends(db_session)):
    rows = db.execute(select(Lead.status, func.count()).group_by(Lead.status)).all()
    lines = ["# TYPE verdict_workflows gauge"]
    lines.extend(f'verdict_workflows{{status="{state}"}} {count}' for state, count in rows)
    return HTMLResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

