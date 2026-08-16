"""Approval-gated CRM write. The pipeline only ever *proposes* a change set;
nothing applies one automatically. An admin-token-gated endpoint can apply a
pending change set to the fictional CRM tables, gated on `applied_changes` for
idempotency so a replayed approval never double-writes."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AppliedChange, CrmChangeSet, CrmCompany, CrmContact, Lead, QualificationDecision


def _field(field_changes: list, obj: str, field: str) -> str | None:
    for fc in field_changes:
        if fc["object"] == obj and fc["field"] == field:
            return fc["proposed_value"]
    return None


def apply_change_set(db: Session, change_set: CrmChangeSet, note: str | None = None) -> CrmChangeSet:
    if change_set.status == "applied":
        return change_set
    if change_set.status != "pending":
        raise ValueError("Only pending change sets can be approved")
    if db.scalar(select(AppliedChange).where(AppliedChange.change_set_id == change_set.id)):
        change_set.status = "applied"
        db.commit()
        return change_set

    lead = db.get(Lead, change_set.lead_id)
    decision = db.scalar(select(QualificationDecision).where(QualificationDecision.lead_id == lead.id))
    field_changes = change_set.field_changes or []

    company_id = change_set.existing_company_id
    if change_set.company_action == "create":
        company_id = uuid.uuid4().hex[:12]
        db.add(CrmCompany(id=company_id, name=_field(field_changes, "company", "name") or lead.company_name))
        db.flush()
    elif change_set.company_action == "update" and company_id and not db.get(CrmCompany, company_id):
        db.add(CrmCompany(id=company_id, name=lead.company_name))
        db.flush()

    contact_id = change_set.existing_contact_id
    if change_set.contact_action == "create":
        contact_id = uuid.uuid4().hex[:12]
        db.add(
            CrmContact(
                id=contact_id,
                email_normalized=lead.email_normalized,
                company_id=company_id,
                first_name=lead.first_name,
                last_name=lead.last_name,
                job_title=lead.job_title,
                contact_type="prospect",
                qualification_band=decision.band if decision else None,
                qualification_score=decision.score if decision else None,
            )
        )
    elif change_set.contact_action == "update" and contact_id:
        contact = db.get(CrmContact, contact_id)
        if contact and decision:
            contact.qualification_band = decision.band
            contact.qualification_score = decision.score

    change_set.status = "applied"
    change_set.reviewer_note = note
    change_set.reviewed_at = datetime.now(UTC)
    db.add(AppliedChange(change_set_id=change_set.id))
    db.commit()
    return change_set


def reject_change_set(db: Session, change_set: CrmChangeSet, note: str | None = None) -> CrmChangeSet:
    if change_set.status != "pending":
        raise ValueError("Only pending change sets can be rejected")
    change_set.status = "rejected"
    change_set.reviewer_note = note
    change_set.reviewed_at = datetime.now(UTC)
    db.commit()
    return change_set
