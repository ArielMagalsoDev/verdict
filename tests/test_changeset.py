from verdict.domain.changeset import build_crm_change_set, derive_outcome

LEAD = {
    "first_name": "Priya",
    "last_name": "Shah",
    "work_email": "priya@harborlineclinics.com",
    "company_name": "Harborline Clinics",
    "job_title": "Director",
    "message": "We operate 38 outpatient locations and need consistent support reporting.",
}


def test_possible_match_proposes_nothing():
    identity = {
        "match_type": "possible",
        "matched_contact_id": None,
        "matched_company_id": None,
        "candidates": [{"company_id": "c1", "company_name": "X", "reason": "r"}],
    }
    change_set = build_crm_change_set("sub-1", LEAD, identity, [])
    assert change_set["contact_action"] == "none"
    assert change_set["company_action"] == "none"
    assert change_set["field_changes"] == []


def test_confident_match_proposes_update():
    identity = {"match_type": "confident", "matched_contact_id": "p1", "matched_company_id": "c4", "candidates": []}
    facts = [{"field": "industry", "value": "Logistics", "status": "verified"}]
    change_set = build_crm_change_set("sub-2", LEAD, identity, facts)
    assert change_set["contact_action"] == "update"
    assert change_set["company_action"] == "update"
    assert any(fc["field"] == "last_inbound_message" for fc in change_set["field_changes"])


def test_no_match_proposes_create():
    identity = {"match_type": "none", "matched_contact_id": None, "matched_company_id": None, "candidates": []}
    change_set = build_crm_change_set("sub-3", LEAD, identity, [])
    assert change_set["contact_action"] == "create"
    assert change_set["company_action"] == "create"


def test_derive_outcome_confident_wins_over_band():
    identity = {"match_type": "confident"}
    decision = {"band": "sales_ready"}
    assert derive_outcome(identity, decision) == "duplicate_or_merge_review"


def test_derive_outcome_insufficient_evidence_before_possible():
    identity = {"match_type": "possible"}
    decision = {"band": "insufficient_evidence"}
    assert derive_outcome(identity, decision) == "insufficient_evidence"


def test_derive_outcome_possible_before_disqualified():
    identity = {"match_type": "possible"}
    decision = {"band": "disqualified"}
    assert derive_outcome(identity, decision) == "duplicate_or_merge_review"


def test_derive_outcome_qualified_is_the_catch_all():
    identity = {"match_type": "none"}
    decision = {"band": "nurture"}
    assert derive_outcome(identity, decision) == "qualified"
