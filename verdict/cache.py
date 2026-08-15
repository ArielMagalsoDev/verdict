"""Response cache keyed by submission id — port of lib/cache.ts. Guided demo
scenarios are pre-warmed into this so repeated clicks are instant and free,
and the budget-exhausted fallback path always has content."""

from sqlalchemy.orm import Session

from .models import ResponseCache


def get_cached_response(db: Session, cache_key: str) -> dict | None:
    row = db.get(ResponseCache, cache_key)
    return row.response if row else None


def set_cached_response(db: Session, cache_key: str, response: dict) -> None:
    row = db.get(ResponseCache, cache_key)
    if row:
        row.response = response
    else:
        db.add(ResponseCache(cache_key=cache_key, response=response))
    db.commit()
