"""Pure identity-resolution logic — port of lib/identity.ts. No IO, fully
unit-testable. Runs BEFORE enrichment/scoring in the pipeline so a lead that
already exists never triggers wasted research spend.

Deliberately conservative: match_type is "confident" ONLY on an exact
normalized email or exact normalized domain match. Name similarity — even a
perfect 1.0 token-Jaccard score — never promotes past "possible". Auto-
merging on name alone risks attaching a stranger's activity to the wrong
account, which is unrecoverable in a real CRM."""

from .text import email_domain, name_similarity, normalize_domain

POSSIBLE_MATCH_FLOOR = 0.2


def resolve_identity(lead: dict, email_normalized: str, contacts: list, companies: list) -> dict:
    """contacts/companies are lists of objects with .id/.email_normalized/
    .company_id or .id/.name/.domain_normalized (ORM rows or dicts)."""

    def get(obj, attr):
        return obj[attr] if isinstance(obj, dict) else getattr(obj, attr)

    for contact in contacts:
        if get(contact, "email_normalized") == email_normalized:
            return {
                "match_type": "confident",
                "matched_contact_id": get(contact, "id"),
                "matched_company_id": get(contact, "company_id"),
                "candidates": [],
            }

    lead_domain = normalize_domain(lead["website"]) if lead.get("website") else email_domain(lead["work_email"])
    if lead_domain:
        for company in companies:
            if get(company, "domain_normalized") == lead_domain:
                return {
                    "match_type": "confident",
                    "matched_contact_id": None,
                    "matched_company_id": get(company, "id"),
                    "candidates": [],
                }

    scored = []
    for company in companies:
        similarity = name_similarity(lead["company_name"], get(company, "name"))
        if similarity >= POSSIBLE_MATCH_FLOOR:
            scored.append((similarity, get(company, "id"), get(company, "name")))
    scored.sort(key=lambda x: x[0], reverse=True)

    if scored:
        candidates = [
            {
                "company_id": company_id,
                "company_name": company_name,
                "reason": f"name similarity {similarity:.2f} — not domain-confirmed",
            }
            for similarity, company_id, company_name in scored
        ]
        return {
            "match_type": "possible",
            "matched_contact_id": None,
            "matched_company_id": None,
            "candidates": candidates,
        }

    return {"match_type": "none", "matched_contact_id": None, "matched_company_id": None, "candidates": []}
