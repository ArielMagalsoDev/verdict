"""Append-only audit trail — port of lib/audit.ts. Every stage of every run
leaves a real, persisted record, and commits immediately so a poller reading
mid-run state sees stages appear progressively rather than all at once."""

import time
from collections.abc import Callable

from sqlalchemy.orm import Session

from .models import AuditEvent


def record_audit_event(
    db: Session,
    lead_id,
    event_type: str,
    status: str,
    summary: str,
    duration_ms: int | None = None,
    external_reference: str | None = None,
) -> None:
    db.add(
        AuditEvent(
            lead_id=lead_id,
            event_type=event_type,
            status=status,
            summary=summary,
            duration_ms=duration_ms,
            external_reference=external_reference,
        )
    )
    db.commit()


def with_audit[T](
    db: Session,
    lead_id,
    event_type: str,
    fn: Callable[[], T],
    summarize: Callable[[T], str],
) -> T:
    """Small helper so pipeline stages don't hand-roll started/completed/
    failed pairs. Commits after each half so a concurrent poller sees stages
    land one at a time."""
    started = time.monotonic()
    record_audit_event(db, lead_id, event_type, "started", f"{event_type} started")

    try:
        result = fn()
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        record_audit_event(db, lead_id, event_type, "failed", str(exc), duration_ms=duration_ms)
        raise

    duration_ms = int((time.monotonic() - started) * 1000)
    record_audit_event(db, lead_id, event_type, "completed", summarize(result), duration_ms=duration_ms)
    return result
