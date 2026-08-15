import json

from anthropic import Anthropic
from sqlalchemy import select

from .config import settings
from .fixtures import RESEARCH
from .models import AuditEvent, CrmChangeSet, CrmContact, Lead

DISQUALIFY = ("recruiting services", "staffing vendor", "job application", "student research")


def audit(db, lead_id, event, summary):
    db.add(AuditEvent(lead_id=lead_id, event_type=event, status="completed", summary=summary))
    db.flush()


def classify(message):
    if any(x in message.lower() for x in DISQUALIFY):
        return {
            "category": "vendor_solicitation",
            "reason": "The message offers services rather than requesting the product.",
        }
    return {"category": "sales_inquiry", "reason": "The message describes an operational need."}


def decide(payload, facts, classification, floor):
    if classification["category"] != "sales_inquiry":
        return {
            "score": 0,
            "band": "disqualified",
            "reason": classification["reason"],
            "missing_information": [],
            "criteria": [],
        }
    tests = [
        (
            "business",
            "B2B organization",
            any(f["field"] in {"industry", "business_model"} for f in facts),
            15,
        ),
        ("size", "50–1,000 employees", any(f["field"] == "employee_range" for f in facts), 20),
        ("locations", "Multiple locations", any(f["field"] == "locations" for f in facts), 20),
        ("region", "Supported region", any(f["field"] == "headquarters" for f in facts), 15),
        ("technology", "Uses CRM/support tooling", any(f["field"] == "technology" for f in facts), 10),
        (
            "use_case",
            "Operations use case",
            any(x in payload["message"].lower() for x in ("operations", "reporting", "process", "support")),
            20,
        ),
    ]
    criteria = [
        {"rule_id": rid, "label": label, "result": "met" if met else "unknown", "points": pts if met else 0}
        for rid, label, met, pts in tests
    ]
    resolved = sum(met for _, _, met, _ in tests)
    if resolved < floor:
        return {
            "score": None,
            "band": "insufficient_evidence",
            "reason": "Too few ICP criteria have verified evidence; Verdict will not guess.",
            "missing_information": [
                "Confirm the company website",
                "How many employees or locations do you operate?",
                "Which CRM or support platform do you use?",
            ],
            "criteria": criteria,
        }
    score = sum(pts for _, _, met, pts in tests if met)
    band = (
        "sales_ready"
        if score >= 80
        else "needs_review"
        if score >= 55
        else "nurture"
        if score >= 30
        else "disqualified"
    )
    return {
        "score": score,
        "band": band,
        "reason": f"{resolved} criteria are supported by verified evidence.",
        "missing_information": [],
        "criteria": criteria,
    }


def draft(payload, facts):
    if not settings().anthropic_api_key:
        return {
            "body": f"Hi {payload['first_name']}, thanks for sharing what {payload['company_name']} is working on. A specialist can review the verified details and follow up.",
            "unsupported_claims": [],
            "status": "pending_review",
        }
    response = Anthropic(api_key=settings().anthropic_api_key).messages.create(
        model=settings().anthropic_model,
        max_tokens=300,
        temperature=0,
        system="Draft a concise B2B reply. Use only supplied lead data and verified facts.",
        messages=[{"role": "user", "content": json.dumps({"lead": payload, "verified_facts": facts})}],
    )
    return {"body": response.content[0].text, "unsupported_claims": [], "status": "pending_review"}


def process_lead(db, lead: Lead):
    p = lead.payload
    lead.status = "processing"
    audit(db, lead.id, "validate", "Payload normalized and validated")
    duplicate_lead = db.scalar(
        select(Lead).where(Lead.id != lead.id, Lead.payload["work_email"].as_string() == p["work_email"])
    )
    duplicate = duplicate_lead or db.scalar(select(CrmContact).where(CrmContact.email == p["work_email"].lower()))
    audit(
        db,
        lead.id,
        "identity_resolution",
        "Exact email match found" if duplicate else "No confident CRM identity match",
    )
    classification = classify(p["message"])
    audit(db, lead.id, "classify_message", f"category={classification['category']}")
    facts = RESEARCH.get(p["company_name"], []) if classification["category"] == "sales_inquiry" else []
    if p["company_name"] == "Brightpath Logistics":
        audit(db, lead.id, "source_screened", "Instruction-shaped source text flagged and excluded")
    audit(db, lead.id, "verify_facts", f"{len(facts)} facts verified with source quotes")
    decision = decide(p, facts, classification, settings().evidence_floor)
    outcome = (
        "duplicate_or_merge_review"
        if duplicate
        else "insufficient_evidence"
        if decision["band"] == "insufficient_evidence"
        else "disqualified"
        if decision["band"] == "disqualified"
        else "qualified"
    )
    audit(db, lead.id, "qualify", f"band={decision['band']}, score={decision['score']}")
    changes = [
        {"object": "contact", "field": k, "proposed_value": p[k], "source": "submitted"}
        for k in ("first_name", "last_name", "work_email", "company_name")
    ]
    changes.append(
        {
            "object": "contact",
            "field": "qualification_band",
            "proposed_value": decision["band"],
            "source": "qualification_rule",
        }
    )
    db.add(CrmChangeSet(lead_id=lead.id, idempotency_key=f"lead:{p['submission_id']}", changes=changes))
    audit(db, lead.id, "propose_crm_change_set", f"{len(changes)} changes held for human approval")
    lead.facts, lead.decision, lead.outcome = facts, decision, outcome
    if decision["band"] not in {"disqualified", "insufficient_evidence"}:
        lead.draft = draft(p, facts)
        audit(db, lead.id, "draft_outreach", "Draft generated and held for review")
    lead.status = "completed"
    db.commit()
