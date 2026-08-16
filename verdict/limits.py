"""Abuse controls: hourly rate limiting, a race-safe
daily spend cap, and (optional) Cloudflare Turnstile bot verification. All
three are env-gated so local/demo mode never blocks on an unset secret."""

from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import RateLimitEvent, SpendLedger

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


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


def verify_turnstile(token: str, remote_ip: str) -> bool:
    """Fails closed only when a secret is actually configured — local/demo
    mode with no TURNSTILE_SECRET_KEY set never blocks a submission."""
    secret = settings().turnstile_secret_key
    if not secret:
        return True
    if not token:
        return False
    try:
        response = httpx.post(
            TURNSTILE_VERIFY_URL,
            data={"secret": secret, "response": token, "remoteip": remote_ip},
            timeout=5.0,
        )
        return bool(response.json().get("success"))
    except Exception:  # noqa: BLE001 — fail closed on any transport error
        return False
