from datetime import UTC, datetime

from sqlalchemy import select

from verdict.domain.validate import validate_lead
from verdict.fixtures import DEMO_SCENARIOS
from verdict.models import Lead, OutreachDraft, SpendLedger
from verdict.pipeline import process_lead


def _create_completed_lead(db, scenario_key="sales-ready"):
    scenario = next(s for s in DEMO_SCENARIOS if s["key"] == scenario_key)
    lead_dict, email_normalized, _ = validate_lead(scenario["lead"])
    lead = Lead(
        submission_id=lead_dict["submission_id"],
        source=lead_dict["source"],
        first_name=lead_dict["first_name"],
        last_name=lead_dict["last_name"],
        work_email=lead_dict["work_email"],
        email_normalized=email_normalized,
        company_name=lead_dict["company_name"],
        website=lead_dict["website"],
        job_title=lead_dict["job_title"],
        country=lead_dict["country"],
        message=lead_dict["message"],
        consent_to_contact=lead_dict["consent_to_contact"],
        status="processing",
        scenario_key=scenario["key"],
    )
    db.add(lead)
    db.commit()
    process_lead(db, lead)
    return lead


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def test_all_html_pages_return_200(client):
    for path in ["/", "/demo", "/architecture", "/evals", "/operations"]:
        res = client.get(path)
        assert res.status_code == 200, path


def test_source_page_200_for_known_slug_404_for_unknown(client):
    assert client.get("/sources/harborline-clinics-about").status_code == 200
    assert client.get("/sources/does-not-exist").status_code == 404


# ---------------------------------------------------------------------------
# Lead intake
# ---------------------------------------------------------------------------
def test_scenario_submission_returns_202(client):
    res = client.post("/api/v1/scenarios/sales-ready", json={})
    assert res.status_code == 202
    body = res.json()
    assert body["status_url"].startswith("/api/v1/leads/")


def test_scenario_submission_is_idempotent(client):
    first = client.post("/api/v1/scenarios/sales-ready", json={})
    second = client.post("/api/v1/scenarios/sales-ready", json={})
    assert first.json()["lead_id"] == second.json()["lead_id"]
    assert second.json()["replayed"] is True


def test_failed_permanent_lead_is_retried_not_replayed(client, db_session):
    import uuid

    from verdict.models import Job

    first = client.post("/api/v1/scenarios/sales-ready", json={}).json()
    lead = db_session.get(Lead, uuid.UUID(first["lead_id"]))
    lead.status = "failed_permanent"
    job = db_session.scalar(select(Job).where(Job.lead_id == lead.id))
    job.status = "failed_permanent"
    job.last_error = "simulated transient failure"
    db_session.commit()

    second = client.post("/api/v1/scenarios/sales-ready", json={}).json()
    assert second["lead_id"] == first["lead_id"]
    assert second["replayed"] is False
    db_session.expire_all()
    assert db_session.get(Lead, lead.id).status != "failed_permanent"


def test_unknown_scenario_key_404s(client):
    res = client.post("/api/v1/scenarios/does-not-exist", json={})
    assert res.status_code == 404


def test_raw_lead_validation_failure_returns_422(client):
    res = client.post("/api/v1/leads", json={"source": "website", "consent_to_contact": True})
    assert res.status_code == 422
    body = res.json()
    assert body["error"] == "validation_failed"
    assert len(body["details"]) > 0


def test_get_lead_state_reflects_completed_pipeline(client, db_session):
    lead = _create_completed_lead(db_session)
    res = client.get(f"/api/v1/leads/{lead.id}")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    assert body["outcome"] == "qualified"
    assert body["lead"]["company_name"] == "Harborline Clinics"
    assert body["decision"]["score"] == 100
    assert len(body["audit_events"]) > 0


def test_get_lead_state_404s_for_unknown_id(client):
    import uuid

    res = client.get(f"/api/v1/leads/{uuid.uuid4()}")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Draft approval
# ---------------------------------------------------------------------------
def test_draft_approve_happy_path(client, db_session):
    lead = _create_completed_lead(db_session)
    res = client.post(f"/api/v1/leads/{lead.id}/draft", json={"action": "approve"})
    assert res.status_code == 200
    assert res.json()["draft"]["status"] == "approved"


def test_draft_reject_happy_path(client, db_session):
    lead = _create_completed_lead(db_session)
    res = client.post(f"/api/v1/leads/{lead.id}/draft", json={"action": "reject"})
    assert res.status_code == 200
    assert res.json()["draft"]["status"] == "rejected"


def test_draft_approve_blocked_when_unsupported_claims_present(client, db_session):
    lead = _create_completed_lead(db_session)
    draft = db_session.scalar(select(OutreachDraft).where(OutreachDraft.lead_id == lead.id))
    draft.unsupported_claims = ["an unverifiable claim"]
    db_session.commit()

    res = client.post(f"/api/v1/leads/{lead.id}/draft", json={"action": "approve"})
    assert res.status_code == 409


# ---------------------------------------------------------------------------
# Admin-gated CRM approval
# ---------------------------------------------------------------------------
def test_crm_change_set_approve_requires_admin_token(client, db_session):
    from verdict.models import CrmChangeSet

    lead = _create_completed_lead(db_session)
    cs = db_session.scalar(select(CrmChangeSet).where(CrmChangeSet.lead_id == lead.id))

    unauthorized = client.post(f"/api/v1/crm-change-sets/{cs.id}/approve")
    assert unauthorized.status_code == 401

    authorized = client.post(
        f"/api/v1/crm-change-sets/{cs.id}/approve", headers={"X-Admin-Token": "test-admin-token"}
    )
    assert authorized.status_code == 200
    assert authorized.json()["status"] == "applied"

    # Idempotent: approving again is a no-op, not an error.
    again = client.post(f"/api/v1/crm-change-sets/{cs.id}/approve", headers={"X-Admin-Token": "test-admin-token"})
    assert again.status_code == 200


def test_admin_delete_lead_requires_token_and_removes_all_child_rows(client, db_session):
    lead = _create_completed_lead(db_session)
    lead_id = lead.id

    unauthorized = client.delete(f"/api/v1/admin/leads/{lead_id}")
    assert unauthorized.status_code == 401

    res = client.delete(f"/api/v1/admin/leads/{lead_id}", headers={"X-Admin-Token": "test-admin-token"})
    assert res.status_code == 200
    assert res.json()["status"] == "deleted"

    assert client.get(f"/api/v1/leads/{lead_id}").status_code == 404
    db_session.expire_all()
    assert db_session.get(Lead, lead_id) is None
    assert db_session.scalar(select(OutreachDraft).where(OutreachDraft.lead_id == lead_id)) is None

    missing = client.delete(f"/api/v1/admin/leads/{lead_id}", headers={"X-Admin-Token": "test-admin-token"})
    assert missing.status_code == 404


# ---------------------------------------------------------------------------
# Abuse controls
# ---------------------------------------------------------------------------
def test_rate_limit_blocks_after_the_configured_ceiling(client):
    last = None
    for i in range(21):
        last = client.post(
            "/api/v1/leads",
            json={
                "submission_id": f"rate-limit-test-{i}",
                "source": "website",
                "first_name": "Test",
                "last_name": "User",
                "work_email": f"test{i}@example.com",
                "company_name": "Example Co",
                "message": "We want to improve our operations process across sites.",
                "consent_to_contact": True,
            },
        )
    assert last.status_code == 429
    assert last.json()["error"] == "rate_limited"


def test_inline_processing_mode_completes_before_the_response_is_returned(client, monkeypatch):
    """Serverless platforms (Vercel and similar) can't run the persistent
    verdict-worker process, so Settings.inline_processing makes the API
    request itself run the pipeline synchronously. Verify a lead is already
    `completed` the instant the 202 response comes back, with no worker
    involved at all."""
    from verdict.config import settings

    monkeypatch.setenv("INLINE_PROCESSING", "true")
    settings.cache_clear()
    try:
        res = client.post("/api/v1/scenarios/sales-ready", json={})
        assert res.status_code == 202
        lead_id = res.json()["lead_id"]

        state = client.get(f"/api/v1/leads/{lead_id}").json()
        assert state["status"] == "completed"
        assert state["outcome"] == "qualified"
        assert state["decision"]["score"] == 100
    finally:
        settings.cache_clear()  # restore default (inline_processing=False) for later tests


def test_budget_exhausted_blocks_new_leads_but_not_replays(client, db_session):
    lead = _create_completed_lead(db_session, "sales-ready")

    today_row = db_session.get(SpendLedger, datetime.now(UTC).date())
    if today_row is None:
        today_row = SpendLedger(day=datetime.now(UTC).date(), spend_usd=0.0)
        db_session.add(today_row)
    today_row.spend_usd = 5.0
    db_session.commit()

    # A brand-new lead should be blocked once the daily cap is reserved.
    blocked = client.post(
        "/api/v1/leads",
        json={
            "submission_id": "budget-test-new-lead",
            "source": "website",
            "first_name": "Test",
            "last_name": "User",
            "work_email": "budget@example.com",
            "company_name": "Example Co",
            "message": "We want to improve our operations process across sites.",
            "consent_to_contact": True,
        },
    )
    assert blocked.status_code == 503
    assert blocked.json()["error"] == "budget_exhausted"

    # But replaying the already-completed guided scenario still works.
    replayed = client.post("/api/v1/scenarios/sales-ready", json={})
    assert replayed.status_code == 202
    assert replayed.json()["replayed"] is True
    assert replayed.json()["lead_id"] == str(lead.id)
