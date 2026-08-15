from verdict.pipeline import classify, decide


def test_vendor_is_disqualified():
    c = classify("We provide recruiting services and want to be your staffing vendor")
    d = decide({"message": "vendor"}, [], c, 4)
    assert d["band"] == "disqualified"
    assert d["score"] == 0


def test_thin_evidence_never_gets_score():
    d = decide({"message": "Help improve our process"}, [], {"category": "sales_inquiry"}, 4)
    assert d["band"] == "insufficient_evidence"
    assert d["score"] is None
    assert d["missing_information"]


def test_scoring_is_deterministic():
    facts = [{"field": x} for x in ("industry", "employee_range", "headquarters", "locations", "technology")]
    d = decide({"message": "Operations reporting"}, facts, {"category": "sales_inquiry"}, 4)
    assert d["band"] == "sales_ready"
    assert d["score"] == 100
