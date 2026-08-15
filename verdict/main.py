from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .config import settings
from .crm import apply_change_set, reject_change_set
from .db import init_db, session_scope
from .fixtures import SCENARIOS, SOURCES
from .models import AuditEvent, CrmChangeSet, CrmContact, Job, Lead
from .schemas import LeadAccepted, LeadIn

ROOT = Path(__file__).parent
templates = Jinja2Templates(directory=ROOT / "templates")


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(title="Verdict", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


def db_session():
    with session_scope() as db:
        yield db


def admin(x_admin_token: str = Header(default="")):
    if x_admin_token != settings().admin_token:
        raise HTTPException(401, "Admin token required")


def serialize(db, lead):
    events = db.scalars(
        select(AuditEvent).where(AuditEvent.lead_id == lead.id).order_by(AuditEvent.created_at)
    ).all()
    cs = db.scalar(select(CrmChangeSet).where(CrmChangeSet.lead_id == lead.id))
    return {
        "id": str(lead.id),
        "status": lead.status,
        "outcome": lead.outcome,
        "lead": lead.payload,
        "facts": lead.facts,
        "decision": lead.decision,
        "draft": lead.draft,
        "change_set": None if not cs else {"id": str(cs.id), "status": cs.status, "changes": cs.changes},
        "audit_events": [
            {
                "event_type": e.event_type,
                "status": e.status,
                "summary": e.summary,
                "timestamp": e.created_at.isoformat(),
            }
            for e in events
        ],
    }


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {"page": "home"})


@app.get("/demo", response_class=HTMLResponse)
def demo(request: Request):
    return templates.TemplateResponse(request, "demo.html", {"page": "demo", "scenarios": SCENARIOS})


@app.get("/architecture", response_class=HTMLResponse)
def architecture(request: Request):
    return templates.TemplateResponse(request, "architecture.html", {"page": "architecture"})


@app.get("/operations", response_class=HTMLResponse)
def operations(request: Request, db: Session = Depends(db_session)):
    counts = dict(db.execute(select(Lead.status, func.count()).group_by(Lead.status)).all())
    recent = db.scalars(select(Lead).order_by(Lead.created_at.desc()).limit(20)).all()
    return templates.TemplateResponse(
        request, "operations.html", {"page": "operations", "counts": counts, "recent": recent}
    )


@app.get("/evals", response_class=HTMLResponse)
def evals(request: Request):
    return templates.TemplateResponse(request, "evals.html", {"page": "evals"})


@app.get("/sources/{slug}", response_class=HTMLResponse)
def source(request: Request, slug: str):
    if slug not in SOURCES:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "source.html", {"slug": slug, "content": SOURCES[slug]})


@app.post("/api/v1/leads", response_model=LeadAccepted, status_code=202)
def create_lead(data: LeadIn, db: Session = Depends(db_session)):
    existing = db.scalar(select(Lead).where(Lead.submission_id == str(data.submission_id)))
    if existing:
        job = db.scalar(select(Job).where(Job.lead_id == existing.id))
        return LeadAccepted(
            lead_id=existing.id,
            job_id=job.id,
            status=existing.status,
            status_url=f"/api/v1/leads/{existing.id}",
        )
    lead = Lead(submission_id=str(data.submission_id), payload=data.model_dump(mode="json"))
    db.add(lead)
    db.flush()
    job = Job(lead_id=lead.id)
    db.add(job)
    db.commit()
    return LeadAccepted(lead_id=lead.id, job_id=job.id, status_url=f"/api/v1/leads/{lead.id}")


@app.post("/api/v1/scenarios/{key}", response_model=LeadAccepted, status_code=202)
def scenario(key: str, db: Session = Depends(db_session)):
    if key not in SCENARIOS:
        raise HTTPException(404)
    data = LeadIn(**SCENARIOS[key]["lead"])
    if key == "duplicate":
        existing = db.scalar(select(CrmContact).where(CrmContact.email == str(data.work_email).lower()))
        if not existing:
            db.add(CrmContact(email=str(data.work_email).lower(), first_name="Tess", last_name="Morgan", company_name="TalentForge"))
            db.commit()
    return create_lead(data, db)


@app.get("/api/v1/leads/{lead_id}")
def get_lead(lead_id: UUID, db: Session = Depends(db_session)):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404)
    return serialize(db, lead)


@app.post("/api/v1/crm-change-sets/{change_id}/approve", dependencies=[Depends(admin)])
def approve(change_id: UUID, db: Session = Depends(db_session)):
    cs = db.get(CrmChangeSet, change_id)
    if not cs:
        raise HTTPException(404)
    try:
        apply_change_set(db, cs)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"id": str(cs.id), "status": cs.status}


@app.post("/api/v1/crm-change-sets/{change_id}/reject", dependencies=[Depends(admin)])
def reject(change_id: UUID, db: Session = Depends(db_session)):
    cs = db.get(CrmChangeSet, change_id)
    if not cs:
        raise HTTPException(404)
    try:
        reject_change_set(db, cs)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"id": str(cs.id), "status": cs.status}


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready(db: Session = Depends(db_session)):
    db.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.get("/metrics")
def metrics(db: Session = Depends(db_session)):
    rows = db.execute(select(Lead.status, func.count()).group_by(Lead.status)).all()
    lines = ["# TYPE verdict_workflows gauge"]
    lines.extend(f'verdict_workflows{{status="{state}"}} {count}' for state, count in rows)
    return HTMLResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")
