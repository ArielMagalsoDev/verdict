"""Ordinary code, not an LLM — CRM-field merge precedence is deterministic.
Port of lib/changeset.ts. Always propose-then-apply: this only builds the
diff a human/UI reviews; nothing is written to the CRM here.

A "possible" identity match proposes NOTHING (contact_action/company_action
= "none") — never merge automatically when more than one credible match
exists. A human resolves it via the candidate list on the identity match
itself, not via a change set."""


def build_crm_change_set(submission_id: str, lead: dict, identity: dict, facts: list[dict]) -> dict:
    idempotency_key = f"changeset:{submission_id}"

    if identity["match_type"] == "possible":
        return {
            "idempotency_key": idempotency_key,
            "contact_action": "none",
            "company_action": "none",
            "existing_contact_id": None,
            "existing_company_id": None,
            "field_changes": [],
        }

    verified_field_changes = [
        {"object": "company", "field": f["field"], "proposed_value": f["value"], "source": "verified_research"}
        for f in facts
        if f["status"] == "verified" and f.get("value")
    ]

    if identity["match_type"] == "confident":
        return {
            "idempotency_key": idempotency_key,
            "contact_action": "update" if identity.get("matched_contact_id") else "none",
            "company_action": (
                "update" if identity.get("matched_company_id") and verified_field_changes else "none"
            ),
            "existing_contact_id": identity.get("matched_contact_id"),
            "existing_company_id": identity.get("matched_company_id"),
            "field_changes": [
                {
                    "object": "task",
                    "field": "last_inbound_message",
                    "proposed_value": lead["message"],
                    "source": "submitted",
                },
                *verified_field_changes,
            ],
        }

    # match_type == "none": genuinely new — propose creating both records.
    return {
        "idempotency_key": idempotency_key,
        "contact_action": "create",
        "company_action": "create",
        "existing_contact_id": None,
        "existing_company_id": None,
        "field_changes": [
            {"object": "contact", "field": "first_name", "proposed_value": lead["first_name"], "source": "submitted"},
            {"object": "contact", "field": "last_name", "proposed_value": lead["last_name"], "source": "submitted"},
            {"object": "contact", "field": "email", "proposed_value": lead["work_email"], "source": "submitted"},
            {
                "object": "contact",
                "field": "job_title",
                "proposed_value": lead.get("job_title") or "(not provided)",
                "source": "submitted",
            },
            {"object": "company", "field": "name", "proposed_value": lead["company_name"], "source": "submitted"},
            *verified_field_changes,
        ],
    }


def derive_outcome(identity: dict, decision: dict) -> str:
    """Coarse outcome classification driving the demo's headline banner. A
    confident identity match always surfaces as duplicate/merge-review first.
    Otherwise the evidence gate's result takes priority over a merely-
    possible identity match."""
    if identity["match_type"] == "confident":
        return "duplicate_or_merge_review"
    if decision["band"] == "insufficient_evidence":
        return "insufficient_evidence"
    if identity["match_type"] == "possible":
        return "duplicate_or_merge_review"
    if decision["band"] == "disqualified":
        return "disqualified"
    return "qualified"
