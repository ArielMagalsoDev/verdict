"""Pipeline orchestration — stage-for-stage port of lib/pipeline.ts. Stage
order matters and is deliberate: identity resolution runs BEFORE
enrichment/scoring so a lead that already exists never triggers wasted
research spend, and the evidence-sufficiency gate runs BEFORE a score is
computed so thin evidence never produces a number.

Each stage is wrapped in audit.with_audit() and commits immediately, so a
client polling GET /api/v1/leads/{id} mid-run sees stages land one at a
time — the progressive-reveal behavior the original's single blocking
request can't offer."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import record_audit_event, with_audit
from .config import settings
from .domain.changeset import build_crm_change_set
from .domain.classify import classify_message
from .domain.draft import check_draft_claims, draft_outreach
from .domain.enrich import find_research_source
from .domain.identity import resolve_identity
from .domain.notify import notify_sales_ready
from .domain.research import extract_company_facts
from .domain.rules import evaluate_qualification
from .domain.screen import screen_source_text
from .domain.verify import verify_facts
from .models import (
    CompanyFact,
    CrmChangeSet,
    CrmCompany,
    CrmContact,
    IdentityMatch,
    Lead,
    OutreachDraft,
    QualificationDecision,
)

HARD_DISQUALIFY_CATEGORIES = {"vendor_solicitation", "job_application", "student_research"}
DRAFTABLE_BANDS = {"sales_ready", "needs_review", "nurture"}


def lead_to_dict(lead: Lead) -> dict:
    return {
        "first_name": lead.first_name,
        "last_name": lead.last_name,
        "work_email": lead.work_email,
        "company_name": lead.company_name,
        "website": lead.website,
        "job_title": lead.job_title,
        "country": lead.country,
        "message": lead.message,
        "consent_to_contact": lead.consent_to_contact,
    }


def _clear_partial_state(db: Session, lead_id) -> None:
    """Retry idempotency: the original TS pipeline never retried (no worker
    drains it — each run happens inline in the POST handler). This port's
    durable worker does retry on failure, so a resumed attempt must wipe any
    partial child rows first rather than risk duplicate facts/decisions."""
    db.query(IdentityMatch).filter(IdentityMatch.lead_id == lead_id).delete()
    db.query(CompanyFact).filter(CompanyFact.lead_id == lead_id).delete()
    db.query(QualificationDecision).filter(QualificationDecision.lead_id == lead_id).delete()
    db.query(CrmChangeSet).filter(CrmChangeSet.lead_id == lead_id).delete()
    db.query(OutreachDraft).filter(OutreachDraft.lead_id == lead_id).delete()
    db.commit()


def process_lead(db: Session, lead: Lead) -> None:
    lead_id = lead.id
    lead_dict = lead_to_dict(lead)

    if db.scalar(select(IdentityMatch).where(IdentityMatch.lead_id == lead_id)):
        record_audit_event(
            db, lead_id, "retry_started", "started",
            "Reprocessing after a prior attempt did not complete — partial state cleared first.",
        )
        _clear_partial_state(db, lead_id)

    # ---- 1. identity resolution (before any research/model spend) ----
    contacts = db.scalars(select(CrmContact)).all()
    companies = db.scalars(select(CrmCompany)).all()
    identity = with_audit(
        db, lead_id, "identity_resolution",
        lambda: resolve_identity(lead_dict, lead.email_normalized, contacts, companies),
        lambda r: f"match_type={r['match_type']}"
        + (f", {len(r['candidates'])} candidate(s)" if r["candidates"] else ""),
    )
    db.add(
        IdentityMatch(
            lead_id=lead_id,
            match_type=identity["match_type"],
            matched_contact_id=identity["matched_contact_id"],
            matched_company_id=identity["matched_company_id"],
            candidates=identity["candidates"],
        )
    )
    db.commit()

    # ---- 2. classify message ----
    classification = with_audit(
        db, lead_id, "classify_message",
        lambda: classify_message(lead.message),
        lambda c: f"category={c['category']}",
    )
    hard_disqualified = classification["category"] in HARD_DISQUALIFY_CATEGORIES

    # ---- 3-5. research + screen + extract + verify (skipped when hard-disqualified) ----
    facts: list[dict] = []
    if not hard_disqualified:
        page = with_audit(
            db, lead_id, "find_research_source",
            lambda: find_research_source(db, lead_dict, identity),
            lambda p: f"source={p['slug']}" if p else "no source found — enrichment yields no facts",
        )

        if page:
            screened = screen_source_text(page["content"])
            if screened["flagged"]:
                record_audit_event(
                    db, lead_id, "source_screened", "completed",
                    "Source content matched suspicious pattern(s): "
                    f"{', '.join(screened['matched_patterns'])}. Extraction and verification still "
                    "run — this is a flag for the audit trail, not a block.",
                    external_reference=page["slug"],
                )

            extracted = with_audit(
                db, lead_id, "extract_facts",
                lambda: extract_company_facts(page),
                lambda f: f"{len(f)} candidate fact(s) extracted",
            )

            verification = with_audit(
                db, lead_id, "verify_facts",
                lambda: verify_facts(extracted, page["content"]),
                lambda r: f"{len(r['verified'])} verified, {len(r['rejected'])} rejected",
            )
            facts = verification["verified"]
            if verification["rejected"]:
                record_audit_event(
                    db, lead_id, "facts_rejected", "completed",
                    " | ".join(
                        f"{r['fact']['field']}=\"{r['fact']['value']}\": {r['reason']}"
                        for r in verification["rejected"]
                    ),
                    external_reference=page["slug"],
                )

            for f in facts:
                db.add(
                    CompanyFact(
                        lead_id=lead_id,
                        field=f["field"],
                        value=f["value"],
                        quote=f.get("quote"),
                        source_url=f["source_url"],
                        source_title=f["source_title"],
                        retrieved_at=datetime.fromisoformat(f["retrieved_at"]),
                        confidence=f["confidence"],
                        status=f["status"],
                    )
                )
            db.commit()

    # ---- 6. evidence-sufficiency gate + scoring ----
    decision = with_audit(
        db, lead_id, "qualify",
        lambda: evaluate_qualification(str(lead_id), lead_dict, facts, classification, settings().evidence_floor),
        lambda d: f"band={d['band']}, score={d['score'] if d['score'] is not None else 'null'}",
    )
    db.add(
        QualificationDecision(
            lead_id=lead_id,
            score=decision["score"],
            band=decision["band"],
            criteria=decision["criteria"],
            reason=decision["reason"],
            missing_information=decision["missing_information"],
            recommended_owner=decision.get("recommended_owner"),
            recommended_action=decision["recommended_action"],
            ruleset_version=decision["ruleset_version"],
        )
    )
    db.commit()

    # ---- extension point: opt-in, best-effort, never affects the decision ----
    notify_sales_ready(
        {
            "lead_id": str(lead_id),
            "band": decision["band"],
            "score": decision["score"],
            "first_name": lead.first_name,
            "last_name": lead.last_name,
            "company_name": lead.company_name,
            "work_email": lead.work_email,
            "job_title": lead.job_title,
            "message": lead.message,
            "reason": decision["reason"],
            "recommended_action": decision["recommended_action"],
        }
    )

    # ---- 8. propose CRM change set (a diff, never a write) ----
    change_set = build_crm_change_set(lead.submission_id, lead_dict, identity, facts)
    with_audit(
        db, lead_id, "propose_crm_change_set",
        lambda: change_set,
        lambda cs: f"contact={cs['contact_action']}, company={cs['company_action']}, "
        f"{len(cs['field_changes'])} field change(s)",
    )
    existing = db.scalar(select(CrmChangeSet).where(CrmChangeSet.idempotency_key == change_set["idempotency_key"]))
    if existing:
        record_audit_event(
            db, lead_id, "duplicate_write_prevented", "skipped",
            f"crm_change_sets insert collided on idempotency_key={change_set['idempotency_key']} — "
            "write prevented, not applied twice.",
        )
    else:
        db.add(
            CrmChangeSet(
                lead_id=lead_id,
                idempotency_key=change_set["idempotency_key"],
                contact_action=change_set["contact_action"],
                company_action=change_set["company_action"],
                existing_contact_id=change_set["existing_contact_id"],
                existing_company_id=change_set["existing_company_id"],
                field_changes=change_set["field_changes"],
            )
        )
        db.commit()

    # ---- 9. draft outreach (gated to draftable bands) + independent claim check ----
    if decision["band"] in DRAFTABLE_BANDS:
        drafted = with_audit(
            db, lead_id, "draft_outreach",
            lambda: draft_outreach(lead_dict, facts),
            lambda d: f"{len(d['body'])} chars, {len(d['claims'])} claim(s) to verify",
        )

        # The recipient's own name/title/company are submitted, trusted data
        # — draft.py's system prompt says it may state them, but verification
        # has no way to confirm them without this line.
        recipient_line = (
            f"Recipient: {lead.first_name} {lead.last_name}, "
            f"{lead.job_title or 'unknown title'} at {lead.company_name}"
        )
        grounding_text = "\n".join(
            [recipient_line, lead.message, *[f"{f['field']}: {f['value']}" for f in facts]]
        )
        unsupported = with_audit(
            db, lead_id, "check_draft_claims",
            lambda: check_draft_claims(drafted["claims"], grounding_text),
            lambda u: "all claims supported" if not u else f"{len(u)} unsupported claim(s) — held for review",
        )

        db.add(
            OutreachDraft(
                lead_id=lead_id,
                generated_body=drafted["body"],
                status="pending_review",
                unsupported_claims=unsupported,
            )
        )
        db.commit()

    lead.status = "completed"
    db.commit()
