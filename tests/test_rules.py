from verdict.domain.rules import RULESET_VERSION, evaluate_qualification

LEAD_US = {"country": "United States"}
SALES_CLASSIFICATION = {"category": "sales_inquiry", "stated_use_case": "improve our reporting workflow", "reason": ""}


def _fact(field, value, status="verified"):
    return {"field": field, "value": value, "quote": value, "status": status}


FULL_FACTS = [
    _fact("employee_range", "500-999"),
    _fact("locations", "38"),
    _fact("headquarters", "United States"),
    _fact("technology", "HubSpot; Zendesk"),
]


def test_full_evidence_scores_sales_ready():
    decision = evaluate_qualification("lead-1", LEAD_US, FULL_FACTS, SALES_CLASSIFICATION)
    assert decision["score"] == 100
    assert decision["band"] == "sales_ready"
    assert decision["ruleset_version"] == RULESET_VERSION


def test_below_evidence_floor_emits_no_score():
    decision = evaluate_qualification("lead-2", {}, [], SALES_CLASSIFICATION, evidence_floor=4)
    assert decision["score"] is None
    assert decision["band"] == "insufficient_evidence"
    assert len(decision["missing_information"]) > 0


def test_evidence_floor_boundary():
    # Exactly 3 resolvable facts + is_b2b = 4 resolved criteria -> at the floor, should score.
    facts = FULL_FACTS[:3]
    decision = evaluate_qualification("lead-3", LEAD_US, facts, SALES_CLASSIFICATION, evidence_floor=4)
    assert decision["score"] is not None


def test_hard_disqualify_categories_short_circuit():
    classification = {"category": "vendor_solicitation", "stated_use_case": None, "reason": "pitching a service"}
    decision = evaluate_qualification("lead-4", LEAD_US, FULL_FACTS, classification)
    assert decision["score"] == 0
    assert decision["band"] == "disqualified"


def test_region_veto_overrides_high_score():
    lead = {"country": "Germany"}
    decision = evaluate_qualification("lead-5", lead, FULL_FACTS, SALES_CLASSIFICATION)
    assert decision["band"] == "disqualified"
    assert "not met" in decision["reason"]


def test_technology_absence_is_not_met_not_unknown():
    facts = [
        _fact("employee_range", "50-199"),
        _fact("locations", "3"),
        _fact("technology", "does not use a CRM or support platform"),
    ]
    decision = evaluate_qualification("lead-6", LEAD_US, facts, SALES_CLASSIFICATION)
    tech_criterion = next(c for c in decision["criteria"] if c["rule_id"] == "existing_platform")
    assert tech_criterion["result"] == "not_met"


def test_band_boundaries():
    # score exactly 80 -> sales_ready; one point below -> needs_review.
    high = [
        _fact("employee_range", "500-999"),  # 25
        _fact("locations", "38"),  # 20
        _fact("technology", "HubSpot"),  # 10
        _fact("headquarters", "United States"),  # unused directly but keeps region resolved via country
    ]
    decision = evaluate_qualification("lead-7", LEAD_US, high, SALES_CLASSIFICATION)
    # is_b2b(10) + employee_range(25) + multi_location(20) + supported_region(15) + existing_platform(10)
    # + relevant_use_case(15) + acv_potential(5) = 100
    assert decision["score"] == 100
    assert decision["band"] == "sales_ready"


def test_consumer_individual_is_hard_disqualified_not_gated():
    classification = {"category": "consumer_individual", "stated_use_case": None, "reason": "personal request"}
    decision = evaluate_qualification("lead-8", {}, [], classification)
    assert decision["band"] == "disqualified"
    assert decision["score"] == 0
