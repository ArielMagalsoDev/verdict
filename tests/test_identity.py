from verdict.domain.identity import resolve_identity
from verdict.domain.text import name_similarity, normalize_company_name

CONTACTS = [{"id": "p1", "email_normalized": "jordan.ruiz@talentbridgerecruiting.com", "company_id": "c4"}]
COMPANIES = [
    {"id": "c1", "name": "Fieldwork Solutions Inc", "domain_normalized": "fieldworksolutions.com"},
    {"id": "c2", "name": "Fieldwork Group Pty", "domain_normalized": "fieldworkgroup.com.au"},
    {"id": "c3", "name": "The Fieldwork Grp", "domain_normalized": "thefieldworkgrp.com"},
    {"id": "c4", "name": "Talent Bridge Recruiting", "domain_normalized": "talentbridgerecruiting.com"},
]


def test_exact_email_match_is_confident():
    lead = {"work_email": "jordan.ruiz@talentbridgerecruiting.com", "company_name": "Talent Bridge Recruiting"}
    result = resolve_identity(lead, "jordan.ruiz@talentbridgerecruiting.com", CONTACTS, COMPANIES)
    assert result["match_type"] == "confident"
    assert result["matched_contact_id"] == "p1"


def test_exact_domain_match_is_confident():
    lead = {"work_email": "someone@fieldworksolutions.com", "company_name": "Fieldwork Solutions Inc"}
    result = resolve_identity(lead, "someone@fieldworksolutions.com", CONTACTS, COMPANIES)
    assert result["match_type"] == "confident"
    assert result["matched_company_id"] == "c1"
    assert result["matched_contact_id"] is None


def test_ambiguous_name_never_promotes_to_confident():
    lead = {"work_email": "marcus@fieldworkgroup.example", "company_name": "Fieldwork Group"}
    result = resolve_identity(lead, "marcus@fieldworkgroup.example", CONTACTS, COMPANIES)
    assert result["match_type"] == "possible"
    assert len(result["candidates"]) == 3  # all three Fieldwork* companies


def test_unrelated_company_resolves_none():
    lead = {"work_email": "someone@example.org", "company_name": "Bright Horizon Partners"}
    result = resolve_identity(lead, "someone@example.org", CONTACTS, COMPANIES)
    assert result["match_type"] == "none"
    assert result["candidates"] == []


def test_name_similarity_below_floor_is_excluded():
    # A single shared, generic token shouldn't necessarily clear the floor on
    # its own — verify the raw similarity math directly.
    assert name_similarity("Acme Corp", "Zenith Holdings") == 0.0


def test_normalize_company_name_strips_suffixes():
    assert normalize_company_name("Fieldwork Group Pty") == "fieldwork"
    assert normalize_company_name("Harborline Clinics, Inc.") == "harborline clinics"
