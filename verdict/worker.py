import time
from datetime import UTC, datetime

from sqlalchemy import select

from .db import init_db, session_scope
from .limits import refund_spend
from .models import Job, Lead
from .pipeline import process_lead
from .seed import seed_crm


def run_once() -> bool:
    with session_scope() as db:
        job = db.scalar(
            select(Job)
            .where(Job.status == "queued", Job.available_at <= datetime.now(UTC))
            .order_by(Job.available_at)
            .with_for_update(skip_locked=True)
        )
        if not job:
            return False
        job.status = "running"
        job.attempts += 1
        job.locked_at = datetime.now(UTC)
        db.commit()
        try:
            process_lead(db, db.get(Lead, job.lead_id))
            job = db.get(Job, job.id)
            job.status = "completed"
            db.commit()
        except Exception as exc:
            db.rollback()
            job = db.get(Job, job.id)
            if job.attempts >= 3:
                job.status = "failed_permanent"
                lead = db.get(Lead, job.lead_id)
                if lead:
                    lead.status = "failed_permanent"
                refund_spend(db)
            else:
                job.status = "queued"
            job.last_error = str(exc)
            db.commit()
        return True


def main() -> None:
    init_db()
    with session_scope() as db:
        seed_crm(db)
    while True:
        if not run_once():
            time.sleep(1)


if __name__ == "__main__":
    main()
