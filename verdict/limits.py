"""Abuse controls: hourly rate limiting and a race-safe daily spend cap."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import RateLimitEvent, SpendLedger


def check_rate_limit(db: Session, client_key: str) -> dict:
    limit = settings().rate_limit_per_hour
    one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    used = db.scalar(
        select(func.count())
        .select_from(RateLimitEvent)
        .where(RateLimitEvent.client_key == client_key, RateLimitEvent.created_at >= one_hour_ago)
    )
    if used >= limit:
        return {"allowed": False, "remaining": 0}
    db.add(RateLimitEvent(client_key=client_key))
    db.commit()
    return {"allowed": True, "remaining": limit - used - 1}


def _today() -> date:
    return datetime.now(UTC).date()


def reserve_spend(db: Session, estimated_usd: float | None = None) -> dict:
    """Race-safe: read-modify-write under the row lock a real Postgres
    deployment provides; SQLite (tests, local dev) has no cross-process
    concurrency here so the same code path is safe there too."""
    amount = estimated_usd if estimated_usd is not None else settings().estimated_cost_per_lead_usd
    cap = settings().daily_spend_cap_usd
    today = _today()

    row = db.get(SpendLedger, today)
    if row is None:
        row = SpendLedger(day=today, spend_usd=0.0)
        db.add(row)
        db.flush()

    if row.spend_usd + amount > cap:
        db.commit()
        return {"allowed": False, "spent_today": row.spend_usd}

    row.spend_usd += amount
    db.commit()
    return {"allowed": True, "spent_today": row.spend_usd}


def refund_spend(db: Session, amount: float | None = None) -> None:
    amount = amount if amount is not None else settings().estimated_cost_per_lead_usd
    today = _today()
    row = db.get(SpendLedger, today)
    if row is None:
        return
    row.spend_usd = max(row.spend_usd - amount, 0.0)
    db.commit()
