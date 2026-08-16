"""Aggregation queries for /operations. Demo-scale data
volume (dozens to low hundreds of rows): fetching and reducing in Python is
simpler and just as correct as a SQL GROUP BY at this scale."""

from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    AuditEvent,
    CompanyFact,
    IdentityMatch,
    Lead,
    OutreachDraft,
    QualificationDecision,
    SpendLedger,
)

STUCK_THRESHOLD_MINUTES = 2  # worst observed real run is a few seconds; generous margin
UNSUPPORTED_FACT_THRESHOLD = 0.02  # CLAUDE.md section 13: "below 2%"


def get_lead_status_counts(db: Session) -> dict:
    return dict(Counter(db.scalars(select(Lead.status))))


def get_band_counts(db: Session) -> dict:
    return dict(Counter(db.scalars(select(QualificationDecision.band))))


def get_identity_match_counts(db: Session) -> dict:
    return dict(Counter(db.scalars(select(IdentityMatch.match_type))))


def get_draft_status_counts(db: Session) -> dict:
    return dict(Counter(db.scalars(select(OutreachDraft.status))))


def get_stage_latency(db: Session) -> list[dict]:
    rows = db.execute(
        select(AuditEvent.event_type, AuditEvent.duration_ms).where(
            AuditEvent.status == "completed", AuditEvent.duration_ms.is_not(None)
        )
    ).all()
    grouped: dict[str, list[int]] = {}
    for event_type, duration_ms in rows:
        grouped.setdefault(event_type, []).append(duration_ms)
    result = [
        {"event_type": event_type, "count": len(durations), "avg_ms": round(sum(durations) / len(durations))}
        for event_type, durations in grouped.items()
    ]
    return sorted(result, key=lambda r: r["avg_ms"], reverse=True)


def get_spend_today(db: Session) -> float:
    row = db.get(SpendLedger, datetime.now(UTC).date())
    return row.spend_usd if row else 0.0


def get_stuck_workflows(db: Session) -> list[dict]:
    cutoff = datetime.now(UTC) - timedelta(minutes=STUCK_THRESHOLD_MINUTES)
    rows = db.scalars(select(Lead).where(Lead.status == "processing", Lead.created_at < cutoff)).all()
    now = datetime.now(UTC)
    return [
        {
            "id": str(lead.id),
            "company_name": lead.company_name,
            "created_at": lead.created_at,
            "minutes_stuck": round((now - lead.created_at).total_seconds() / 60),
        }
        for lead in rows
    ]


def get_duplicate_write_prevented_count(db: Session, hours_back: int = 24) -> int:
    cutoff = datetime.now(UTC) - timedelta(hours=hours_back)
    rows = db.scalars(
        select(AuditEvent.id).where(
            AuditEvent.event_type == "duplicate_write_prevented", AuditEvent.created_at >= cutoff
        )
    ).all()
    return len(rows)


def get_unsupported_fact_rate(db: Session) -> dict:
    rows = db.scalars(select(OutreachDraft.unsupported_claims)).all()
    total = len(rows)
    with_unsupported = sum(1 for claims in rows if claims)
    return {
        "rate": 0.0 if total == 0 else with_unsupported / total,
        "total": total,
        "with_unsupported": with_unsupported,
    }


def evaluate_alerts(
    stuck_workflows: list[dict], duplicate_writes_prevented: int, unsupported_fact_rate: dict
) -> list[dict]:
    """Pure function over already-fetched data — testable without a live DB
    round trip. The 3 v1 alerts from CLAUDE.md section 15."""
    alerts = []

    if stuck_workflows:
        alerts.append(
            {
                "key": "stuck_workflows",
                "severity": "critical",
                "title": f"{len(stuck_workflows)} workflow(s) stuck in \"processing\"",
                "detail": (
                    f"Pending beyond the {STUCK_THRESHOLD_MINUTES}-minute expected-duration "
                    "threshold — likely an unhandled crash before the pipeline's error handling ran."
                ),
            }
        )
    else:
        alerts.append(
            {
                "key": "stuck_workflows",
                "severity": "ok",
                "title": "No stuck workflows",
                "detail": f"All leads resolved within the {STUCK_THRESHOLD_MINUTES}-minute expected-duration window.",
            }
        )

    if duplicate_writes_prevented > 0:
        alerts.append(
            {
                "key": "duplicate_writes",
                "severity": "warn",
                "title": f"{duplicate_writes_prevented} duplicate write(s) prevented in the last 24h",
                "detail": (
                    "This is idempotency working as designed, not a failure — a replayed "
                    "request tried to write twice and was correctly blocked."
                ),
            }
        )
    else:
        alerts.append(
            {
                "key": "duplicate_writes",
                "severity": "ok",
                "title": "No duplicate writes prevented recently",
                "detail": "No replay/duplicate-key collisions in the last 24 hours.",
            }
        )

    pct = round(unsupported_fact_rate["rate"] * 100, 1)
    if unsupported_fact_rate["rate"] > UNSUPPORTED_FACT_THRESHOLD:
        alerts.append(
            {
                "key": "unsupported_fact_rate",
                "severity": "critical",
                "title": f"Unsupported-fact rate {pct}% exceeds the 2% target",
                "detail": (
                    f"{unsupported_fact_rate['with_unsupported']}/{unsupported_fact_rate['total']} drafts had "
                    "at least one claim the verification pass could not confirm."
                ),
            }
        )
    else:
        alerts.append(
            {
                "key": "unsupported_fact_rate",
                "severity": "ok",
                "title": f"Unsupported-fact rate {pct}% — within target",
                "detail": (
                    f"{unsupported_fact_rate['with_unsupported']}/{unsupported_fact_rate['total']} drafts had "
                    "an unsupported claim (target: below 2%)."
                ),
            }
        )

    return alerts


def get_company_fact_count(db: Session) -> int:
    return len(db.scalars(select(CompanyFact.id)).all())
