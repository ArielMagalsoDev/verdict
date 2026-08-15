"""Decides which single source page (if any) enrichment researches against —
port of lib/enrich.ts. Deliberately conservative: a "possible" identity
match (ambiguous — more than one credible candidate) or no website at all
means there is no safe source to pick, so this returns None rather than
guessing. That absence is what starves the ICP criteria of evidence and
correctly drives the insufficient-evidence scenario — not a special case,
just the natural consequence of not guessing."""

from sqlalchemy.orm import Session

from ..fixtures.mini_web import find_mini_web_page_by_domain
from ..models import CrmCompany
from .text import normalize_domain


def find_research_source(db: Session, lead: dict, identity: dict) -> dict | None:
    if lead.get("website"):
        page = find_mini_web_page_by_domain(normalize_domain(lead["website"]))
        if page:
            return page

    if identity["match_type"] == "confident" and identity.get("matched_company_id"):
        company = db.get(CrmCompany, identity["matched_company_id"])
        if company and company.domain_normalized:
            page = find_mini_web_page_by_domain(company.domain_normalized)
            if page:
                return page

    return None
