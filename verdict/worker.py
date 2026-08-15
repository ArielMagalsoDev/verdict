import time
from datetime import UTC, datetime

from sqlalchemy import select

from .db import init_db, session_scope
from .models import Job, Lead
from .pipeline import process_lead


def run_once():
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
            job.status = "failed" if job.attempts >= 3 else "queued"
            job.last_error = str(exc)
            db.commit()
        return True


def main():
    init_db()
    while True:
        if not run_once():
            time.sleep(1)


if __name__ == "__main__":
    main()
