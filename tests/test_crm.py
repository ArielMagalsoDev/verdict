import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from verdict.crm import apply_change_set
from verdict.db import Base
from verdict.models import AppliedChange, CrmChangeSet, CrmContact, Lead


def test_approval_is_idempotent_and_writes_contact():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    payload = {
        "submission_id": str(uuid.uuid4()),
        "first_name": "Priya",
        "last_name": "Shah",
        "work_email": "priya@example.com",
        "company_name": "Harborline",
    }
    with Session(engine, expire_on_commit=False) as db:
        lead = Lead(
            submission_id=payload["submission_id"],
            payload=payload,
            status="completed",
            decision={"band": "sales_ready", "score": 90},
            facts=[],
        )
        db.add(lead)
        db.flush()
        change = CrmChangeSet(lead_id=lead.id, idempotency_key=f"lead:{payload['submission_id']}", changes=[])
        db.add(change)
        db.commit()
        apply_change_set(db, change)
        apply_change_set(db, change)
        assert len(db.scalars(select(CrmContact)).all()) == 1
        assert len(db.scalars(select(AppliedChange)).all()) == 1
        assert change.status == "applied"
