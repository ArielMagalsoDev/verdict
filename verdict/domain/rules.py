"""Deterministic ICP scoring engine + evidence-sufficiency gate — port of
Pure function, no IO, every branch unit-testable.

The gate runs BEFORE any score is computed: if fewer than evidence_floor of
the 7 core criteria are resolvable, no numeric score is ever emitted. This is
the single most important behavior in the whole system — a number on thin
evidence is the trust-destroying failure naive lead-scoring AI has, and this
function structurally prevents it, not just discourages it via prompting."""

import re

RULESET_VERSION = "northstar-icp-v1"

CORE_CRITERIA = [
    "is_b2b",
    "employee_range",
    "multi_location",
    "supported_region",
    "existing_platform",
    "relevant_use_case",
    "acv_potential",
]

# Sums to 100 — the 0-100 bands below assume every criterion resolves.
POINTS = {
    "is_b2b": 10,
    "employee_range": 25,
    "multi_location": 20,
    "supported_region": 15,
    "existing_platform": 10,
    "relevant_use_case": 15,
    "acv_potential": 5,
}

LABELS = {
    "is_b2b": "B2B organization",
    "employee_range": "50-1,000 employees",
    "multi_location": "Operates multiple locations or business units",
    "supported_region": "Located in a supported region (US, CA, UK, AU, SG)",
    "existing_platform": "Uses a CRM or support platform",
    "relevant_use_case": "Ops, support, or revenue-ops use case",
    "acv_potential": "Expected annual contract value at least $12,000",
}

# Shown to the visitor/rep when a criterion can't be resolved — this is what
# "insufficient_evidence" hands back instead of a guess.
UNBLOCKING_QUESTIONS = {
    "is_b2b": "Confirm this is a business inquiry, not an individual/consumer request.",
    "employee_range": "Roughly how many employees does the company have?",
    "multi_location": "How many locations or business units do you operate?",
    "supported_region": "What country is the company headquartered in?",
    "existing_platform": "What CRM or support platform do you currently use, if any?",
    "relevant_use_case": "What process are you hoping to improve?",
    "acv_potential": "What's the approximate team size or budget this would need to cover?",
}

SUPPORTED_REGION_TOKENS = [
    "us",
    "usa",
    "united states",
    "ca",
    "canada",
    "uk",
    "united kingdom",
    "au",
    "australia",
    "sg",
    "singapore",
]

# A consumer/individual inquiry is fully resolvable from classification alone
# — waiting on the evidence-sufficiency gate before disqualifying it would
# (a) route it toward "ask for more evidence" instead of a clean reject, and
# (b) risk generating clarifying questions like "how many employees does your
# company have" for someone who was never a company.
HARD_DISQUALIFY = {"vendor_solicitation", "job_application", "student_research", "consumer_individual"}

_RANGE_RE = re.compile(r"(\d+)\D+(\d+)")
_COUNT_RE = re.compile(r"(\d+)")
_MULTI_RE = re.compile(r"multiple|several|locations|sites", re.I)
_ABSENCE_RE_A = re.compile(r"\b(no|not|none|without|doesn't|does not)\b[^.]*\b(crm|platform|software|system)\b", re.I)
_ABSENCE_RE_B = re.compile(r"\b(crm|platform|software|system)\b[^.]*\b(no|not|none)\b", re.I)
_USE_CASE_RE = re.compile(r"ops|operations|support|reporting|workflow|revenue|process", re.I)


def _find_fact(facts: list[dict], field: str) -> dict | None:
    return next((f for f in facts if f["field"] == field), None)


def _unresolved(rule_id: str, evidence: list[str] | None = None) -> dict:
    return {"rule_id": rule_id, "label": LABELS[rule_id], "result": "unknown", "points": 0, "evidence": evidence or []}


def _resolved(rule_id: str, met: bool, evidence: list[str]) -> dict:
    return {
        "rule_id": rule_id,
        "label": LABELS[rule_id],
        "result": "met" if met else "not_met",
        "points": POINTS[rule_id] if met else 0,
        "evidence": evidence,
    }


def _resolve_criterion(rule_id: str, lead: dict, facts: list[dict], classification: dict) -> dict:
    if rule_id == "is_b2b":
        if classification["category"] == "unclear":
            return _unresolved(rule_id, ["message classification"])
        return _resolved(rule_id, classification["category"] != "consumer_individual", ["message classification"])

    if rule_id == "employee_range":
        f = _find_fact(facts, "employee_range")
        if not f or f["status"] == "unknown" or not f.get("value"):
            return _unresolved(rule_id)
        m = _RANGE_RE.search(f["value"])
        if not m:
            return _unresolved(rule_id, ["employee_range"])
        lo, hi = int(m.group(1)), int(m.group(2))
        return _resolved(rule_id, hi >= 50 and lo <= 1000, ["employee_range"])

    if rule_id == "multi_location":
        f = _find_fact(facts, "locations")
        if not f or f["status"] == "unknown" or not f.get("value"):
            return _unresolved(rule_id)
        count_match = _COUNT_RE.search(f["value"])
        met = int(count_match.group(1)) > 1 if count_match else bool(_MULTI_RE.search(f["value"]))
        return _resolved(rule_id, met, ["locations"])

    if rule_id == "supported_region":
        f = _find_fact(facts, "headquarters")
        country = (lead.get("country") or (f["value"] if f else "") or "").lower()
        if not country:
            return _unresolved(rule_id)
        met = any(token in country for token in SUPPORTED_REGION_TOKENS)
        return _resolved(rule_id, met, ["submitted country"] if lead.get("country") else ["headquarters"])

    if rule_id == "existing_platform":
        f = _find_fact(facts, "technology")
        if not f or f["status"] == "unknown" or not f.get("value"):
            return _unresolved(rule_id)
        # A stated absence ("does not use a CRM") is still a technology fact
        # — extraction correctly pulls it — but it means the criterion is NOT
        # met, not met-by-default-because-a-fact-exists.
        states_absence = bool(_ABSENCE_RE_A.search(f["value"]) or _ABSENCE_RE_B.search(f["value"]))
        return _resolved(rule_id, not states_absence, ["technology"])

    if rule_id == "relevant_use_case":
        stated = classification.get("stated_use_case")
        if classification["category"] != "sales_inquiry" or not stated:
            return _unresolved(rule_id, ["message classification"])
        met = bool(_USE_CASE_RE.search(stated))
        return _resolved(rule_id, met, ["message classification"])

    if rule_id == "acv_potential":
        # Derived from company size, not a directly enriched fact.
        # Deliberately conservative — this can basically never resolve past
        # "unknown" without a stated budget signal.
        f = _find_fact(facts, "employee_range")
        if not f or f["status"] == "unknown" or not f.get("value"):
            return _unresolved(rule_id)
        m = _RANGE_RE.search(f["value"])
        hi = int(m.group(2)) if m else 0
        return _resolved(rule_id, hi >= 200, ["employee_range"])

    raise ValueError(f"unknown criterion: {rule_id}")


def evaluate_qualification(
    lead_id: str, lead: dict, facts: list[dict], classification: dict, evidence_floor: int = 4
) -> dict:
    if classification["category"] in HARD_DISQUALIFY:
        return {
            "lead_id": lead_id,
            "score": 0,
            "band": "disqualified",
            "criteria": [],
            "reason": f"Classified as {classification['category'].replace('_', ' ')}: {classification['reason']}",
            "missing_information": [],
            "recommended_action": "Record reason; no sales outreach.",
            "ruleset_version": RULESET_VERSION,
        }

    criteria = [_resolve_criterion(rule_id, lead, facts, classification) for rule_id in CORE_CRITERIA]
    resolved_count = sum(1 for c in criteria if c["result"] != "unknown")

    if resolved_count < evidence_floor:
        missing_information = [UNBLOCKING_QUESTIONS[c["rule_id"]] for c in criteria if c["result"] == "unknown"]
        return {
            "lead_id": lead_id,
            "score": None,
            "band": "insufficient_evidence",
            "criteria": criteria,
            "reason": (
                f"Only {resolved_count}/{len(criteria)} core criteria could be resolved "
                f"(floor: {evidence_floor}). Emitting a score on this little evidence would be "
                "a guess, not a qualification."
            ),
            "missing_information": missing_information,
            "recommended_action": "Send clarification questions; do not assign to a rep yet.",
            "ruleset_version": RULESET_VERSION,
        }

    score = sum(c["points"] for c in criteria)

    # A well-resourced consumer inquiry or out-of-region company is still not
    # a fit, regardless of how high the numeric score climbed on the rest.
    veto = next(
        (c for c in criteria if c["rule_id"] in ("is_b2b", "supported_region") and c["result"] == "not_met"), None
    )

    if veto:
        band = "disqualified"
        recommended_action = "Record reason; no sales outreach."
    elif score >= 80:
        band = "sales_ready"
        recommended_action = "Assign to an account executive after approval."
    elif score >= 55:
        band = "needs_review"
        recommended_action = "Send to an SDR or RevOps queue."
    elif score >= 30:
        band = "nurture"
        recommended_action = "Add to an approved educational sequence."
    else:
        band = "disqualified"
        recommended_action = "Record reason; no sales outreach."

    return {
        "lead_id": lead_id,
        "score": score,
        "band": band,
        "criteria": criteria,
        "reason": (
            f"Disqualified: \"{veto['label']}\" was not met."
            if veto
            else f"Score {score}/100 across {len(criteria)} resolved criteria."
        ),
        "missing_information": [],
        "recommended_action": recommended_action,
        "ruleset_version": RULESET_VERSION,
    }
