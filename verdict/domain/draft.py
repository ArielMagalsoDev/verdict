"""Outreach drafting + independent claim verification.
The fallback path never trusts a self-report either: it builds claims as
literal ``field: value`` fragments that are guaranteed to appear in the same
grounding text the checker reads, so the same fail-closed contract holds
without a model in the loop."""

import re

from ..anthropic_client import llm_enabled, tool_call

DRAFT_TOOL = {
    "name": "record_draft",
    "description": "Draft a short personalized first-touch email.",
    "input_schema": {
        "type": "object",
        "properties": {
            "body": {"type": "string", "description": "3-5 sentence plain-text email body, no subject line."},
            "claims": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Every factual statement the email makes specifically about the recipient or "
                    "their company (not generic Northstar Ops product statements)."
                ),
            },
        },
        "required": ["body", "claims"],
    },
}

DRAFT_SYSTEM_PROMPT = """Draft a short first-touch sales email from Northstar Ops, a workflow and
reporting software company for multi-location service businesses. You may
state a fact about the recipient's company ONLY if it appears in their own
submitted message or in the VERIFIED FACTS list provided — never introduce a
company detail from anywhere else, and never mention pricing, discounts,
contracts, or guarantees (none have been offered). Keep it to 3-5 sentences,
plain text, no subject line, no signature block."""

CLAIM_CHECK_TOOL = {
    "name": "record_claim_check",
    "description": "Check whether each claim is supported by the allowed grounding text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "number"},
                        "supported": {"type": "boolean"},
                    },
                    "required": ["index", "supported"],
                },
            },
        },
        "required": ["results"],
    },
}

CLAIM_CHECK_SYSTEM_PROMPT = """For each claim, decide whether it is directly supported by the grounding
text. Be strict: a claim is supported only if the grounding text states it or
something that directly entails it. Generic statements about Northstar Ops's
own product are always considered supported (they aren't claims about the
recipient)."""


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def _fallback_draft(lead: dict, verified_facts: list[dict]) -> dict:
    claims: list[str] = []
    fact_sentence = ""
    if verified_facts:
        top = verified_facts[0]
        fact_sentence = f" I saw that {lead['company_name']} — {top['field'].replace('_', ' ')}: {top['value']}."
        claims.append(f"{top['field']}: {top['value']}")

    body = (
        f"Hi {lead['first_name']}, thanks for sharing what {lead['company_name']} is working on."
        f"{fact_sentence} A Northstar Ops specialist can review the verified details from your "
        "message and follow up with next steps."
    )
    return {"body": body, "claims": claims}


def draft_outreach(lead: dict, verified_facts: list[dict]) -> dict:
    """Appropriate AI task: drafting from verified facts only."""
    if not llm_enabled():
        return _fallback_draft(lead, verified_facts)

    fact_lines = "\n".join(f"- {f['field']}: {f['value']}" for f in verified_facts) or "(none verified)"
    user = (
        f"RECIPIENT: {lead['first_name']} {lead['last_name']}, {lead.get('job_title') or 'unknown title'} "
        f"at {lead['company_name']}\nSUBMITTED MESSAGE: {lead['message']}\n\nVERIFIED FACTS:\n{fact_lines}"
    )
    result = tool_call(DRAFT_SYSTEM_PROMPT, user, DRAFT_TOOL, max_tokens=512)
    if not result:
        return {"body": "", "claims": []}
    return {"body": result.get("body", ""), "claims": result.get("claims") or []}


def check_draft_claims(claims: list[str], grounding_text: str) -> list[str]:
    """Independently re-verifies the draft's self-reported claims against the
    lead's own message + verified facts — never trusts the drafting call's
    self-report. Returns the subset of claims that could NOT be verified;
    non-empty blocks approval."""
    if not claims:
        return []

    if not llm_enabled():
        ground = _normalize(grounding_text)
        return [c for c in claims if _normalize(c) not in ground]

    import json

    payload = [{"index": i, "claim": c} for i, c in enumerate(claims)]
    user = f"GROUNDING TEXT:\n{grounding_text}\n\nCLAIMS:\n{json.dumps(payload, indent=2)}"
    result = tool_call(CLAIM_CHECK_SYSTEM_PROMPT, user, CLAIM_CHECK_TOOL, max_tokens=512)
    # Fail safe: if verification itself breaks, treat every claim as
    # unsupported rather than silently approving an unverified draft.
    if not result:
        return claims

    unsupported = []
    for r in result.get("results", []):
        idx = r.get("index")
        if idx is not None and 0 <= idx < len(claims) and not r.get("supported"):
            unsupported.append(claims[idx])
    return unsupported
