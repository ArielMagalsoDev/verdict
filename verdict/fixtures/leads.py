"""The four guided demo scenarios — fixed copy, values, and submission ids so
each one always tells the same story."""

# Fixed timestamp — no datetime.now() at module scope, keeps this deterministic.
SUBMITTED_AT = "2026-08-07T09:00:00.000Z"

DEMO_SCENARIOS = [
    {
        "key": "sales-ready",
        "title": "Sales-ready lead",
        "blurb": "Multi-location operator, clear use case, full evidence resolves cleanly.",
        "expected_outcome": "qualified",
        "lead": {
            "submission_id": "demo-sales-ready",
            "source": "website",
            "first_name": "Priya",
            "last_name": "Shah",
            "work_email": "priya.shah@harborlineclinics.com",
            "company_name": "Harborline Clinics",
            "website": "harborlineclinics.com",
            "job_title": "Director of Operations",
            "country": "United States",
            "message": (
                "We operate 38 outpatient locations and need consistent support reporting "
                "across every site. We currently use HubSpot and Zendesk."
            ),
            "consent_to_contact": True,
            "submitted_at": SUBMITTED_AT,
        },
    },
    {
        "key": "insufficient-evidence",
        "title": "Insufficient evidence",
        "blurb": "Ambiguous company identity, thin message — the system declines to guess a score.",
        "expected_outcome": "insufficient_evidence",
        "lead": {
            "submission_id": "demo-insufficient-evidence",
            "source": "website",
            "first_name": "Marcus",
            "last_name": "Lee",
            "work_email": "marcus.lee@fieldworkgroup.example",
            "company_name": "Fieldwork Group",
            "website": None,
            "job_title": "Operations Manager",
            "country": None,
            "message": "We may need help improving our process. Can someone contact me?",
            "consent_to_contact": True,
            "submitted_at": SUBMITTED_AT,
        },
    },
    {
        "key": "duplicate-vendor",
        "title": "Duplicate & poor-fit",
        "blurb": "Matches an existing vendor contact exactly — no duplicate created, no sales outreach.",
        "expected_outcome": "duplicate_or_merge_review",
        "lead": {
            "submission_id": "demo-duplicate-vendor",
            "source": "website",
            "first_name": "Jordan",
            "last_name": "Ruiz",
            "work_email": "jordan.ruiz@talentbridgerecruiting.com",
            "company_name": "Talent Bridge Recruiting",
            "website": None,
            "job_title": "Business Development",
            "country": "United States",
            "message": (
                "Hi, following up to see if Northstar Ops is hiring — we'd love to help you "
                "fill open roles fast with our contingency recruiting service."
            ),
            "consent_to_contact": True,
            "submitted_at": SUBMITTED_AT,
        },
    },
    {
        "key": "prompt-injection",
        "title": "Prompt-injection attempt",
        "blurb": "Researched company page contains an embedded instruction to fake a perfect score.",
        "expected_outcome": "qualified",
        "lead": {
            "submission_id": "demo-prompt-injection",
            "source": "website",
            "first_name": "Devon",
            "last_name": "Cole",
            "work_email": "devon.cole@ridgelinefield.com",
            "company_name": "Ridgeline Field Services",
            "website": "ridgelinefield.com",
            "job_title": "Operations Lead",
            "country": "United States",
            "message": (
                "We're trying to consolidate reporting across our depots instead of chasing "
                "each one separately. Can you tell me more about how Northstar Ops would work for us?"
            ),
            "consent_to_contact": True,
            "submitted_at": SUBMITTED_AT,
        },
    },
]

_BY_KEY = {s["key"]: s for s in DEMO_SCENARIOS}


def find_scenario(key: str) -> dict | None:
    return _BY_KEY.get(key)
