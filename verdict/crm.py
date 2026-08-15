from datetime import UTC, datetime

from sqlalchemy import select

from .models import AppliedChange, CrmChangeSet, CrmContact, Lead


def apply_change_set(db, change_set: CrmChangeSet, note: str | None = None):
    if change_set.status == "applied":
        return change_set
    if change_set.status != "pending":
        raise ValueError("Only pending change sets can be approved")
    if db.scalar(select(AppliedChange).where(AppliedChange.change_set_id == change_set.id)):
        change_set.status = "applied"
        db.commit()
        return change_set
    lead = db.get(Lead, change_set.lead_id)
    p = lead.payload
    contact = db.scalar(select(CrmContact).where(CrmContact.email == p["work_email"].lower()))
    if not contact:
        contact = CrmContact(
            email=p["work_email"].lower(),
            first_name=p["first_name"],
            last_name=p["last_name"],
            company_name=p["company_name"],
        )
        db.add(contact)
    contact.qualification_band = lead.decision["band"]
    contact.qualification_score = lead.decision["score"]
    change_set.status = "applied"
    change_set.reviewer_note = note
    change_set.reviewed_at = datetime.now(UTC)
    db.add(AppliedChange(change_set_id=change_set.id))
    db.commit()
    return change_set


def reject_change_set(db, change_set, note=None):
    if change_set.status != "pending":
        raise ValueError("Only pending change sets can be rejected")
    change_set.status = "rejected"
    change_set.reviewer_note = note
    change_set.reviewed_at = datetime.now(UTC)
    db.commit()
    return change_set
