import re

from sqlalchemy import select

from verdict.domain.changeset import derive_outcome
from verdict.domain.validate import validate_lead
from verdict.fixtures import DEMO_SCENARIOS
from verdict.models import AuditEvent, CompanyFact, IdentityMatch, Lead, OutreachDraft, QualificationDecision
from verdict.pipeline import process_lead

INJECTION_MARKERS = re.compile(
    r"\b(pre-?certified|pre-?approved|qualification_score|skip (all )?checks|40%|"
    r"lifetime discount|pre-?signed contract|guarantee)\b",
    re.I,
)


def _run_scenario(db, scenario):
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


def _outcome_for(db, lead):
    identity_row = db.scalar(select(IdentityMatch).where(IdentityMatch.lead_id == lead.id))
    decision_row = db.scalar(select(QualificationDecision).where(QualificationDecision.lead_id == lead.id))
    identity = {"match_type": identity_row.match_type}
    decision = {"band": decision_row.band}
    return derive_outcome(identity, decision)


def test_all_four_demo_scenarios_reproduce_expected_outcomes(db_session):
    for scenario in DEMO_SCENARIOS:
        lead = _run_scenario(db_session, scenario)
        outcome = _outcome_for(db_session, lead)
        assert outcome == scenario["expected_outcome"], f"{scenario['key']}: got {outcome}"
        assert lead.status == "completed"


def test_prompt_injection_scenario_flags_source_and_leaks_nothing(db_session):
    scenario = next(s for s in DEMO_SCENARIOS if s["key"] == "prompt-injection")
    lead = _run_scenario(db_session, scenario)

    events = db_session.scalars(select(AuditEvent).where(AuditEvent.lead_id == lead.id)).all()
    assert any(e.event_type == "source_screened" for e in events)

    facts = db_session.scalars(select(CompanyFact).where(CompanyFact.lead_id == lead.id)).all()
    draft = db_session.scalar(select(OutreachDraft).where(OutreachDraft.lead_id == lead.id))
    haystack = " | ".join(f"{f.field}:{f.value}" for f in facts) + " | " + (draft.generated_body if draft else "")
    assert not INJECTION_MARKERS.search(haystack)


def test_insufficient_evidence_scenario_emits_no_score(db_session):
    scenario = next(s for s in DEMO_SCENARIOS if s["key"] == "insufficient-evidence")
    lead = _run_scenario(db_session, scenario)
    decision = db_session.scalar(select(QualificationDecision).where(QualificationDecision.lead_id == lead.id))
    assert decision.score is None
    assert len(decision.missing_information) > 0


def test_duplicate_vendor_scenario_matches_seeded_contact(db_session):
    scenario = next(s for s in DEMO_SCENARIOS if s["key"] == "duplicate-vendor")
    lead = _run_scenario(db_session, scenario)
    identity = db_session.scalar(select(IdentityMatch).where(IdentityMatch.lead_id == lead.id))
    assert identity.match_type == "confident"
    assert identity.matched_contact_id == "p1"


def test_retry_reprocessing_does_not_duplicate_facts(db_session):
    scenario = next(s for s in DEMO_SCENARIOS if s["key"] == "sales-ready")
    lead = _run_scenario(db_session, scenario)
    facts_before = db_session.scalars(select(CompanyFact).where(CompanyFact.lead_id == lead.id)).all()

    # Simulate a worker retry re-entering the same (already-completed) lead.
    process_lead(db_session, lead)
    facts_after = db_session.scalars(select(CompanyFact).where(CompanyFact.lead_id == lead.id)).all()

    assert len(facts_after) == len(facts_before)
