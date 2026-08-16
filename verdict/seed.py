"""Seeds the fictional CRM used for identity resolution.

Three
similarly-named "Fieldwork ___" companies power the ambiguous-match scenario,
and Talent Bridge Recruiting + its one contact power the confident-match /
vendor-solicitation scenario. Idempotent — safe to call on every startup.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import CrmCompany, CrmContact

SEED_COMPANIES = [
    {"id": "c1", "name": "Fieldwork Solutions Inc", "domain_normalized": "fieldworksolutions.com"},
    {"id": "c2", "name": "Fieldwork Group Pty", "domain_normalized": "fieldworkgroup.com.au"},
    {"id": "c3", "name": "The Fieldwork Grp", "domain_normalized": "thefieldworkgrp.com"},
    {"id": "c4", "name": "Talent Bridge Recruiting", "domain_normalized": "talentbridgerecruiting.com"},
]

SEED_CONTACTS = [
    {
        "id": "p1",
        "email_normalized": "jordan.ruiz@talentbridgerecruiting.com",
        "company_id": "c4",
        "first_name": "Jordan",
        "last_name": "Ruiz",
        "job_title": "Business Development",
        "contact_type": "vendor",
    },
]


def seed_crm(db: Session) -> None:
    """Idempotent, and safe against a concurrent seeder: on a fresh boot the
    web and worker containers can both reach this within the same moment,
    and a check-then-insert race can still lose to a duplicate-key error even
    with the existence check below. That's fine — it means the other process
    already seeded the row — so a collision here is swallowed, not raised."""
    try:
        for row in SEED_COMPANIES:
            if not db.get(CrmCompany, row["id"]):
                db.add(CrmCompany(**row))
        db.flush()
        for row in SEED_CONTACTS:
            existing = db.scalar(select(CrmContact).where(CrmContact.id == row["id"]))
            if not existing:
                db.add(CrmContact(**row))
        db.commit()
    except IntegrityError:
        db.rollback()
