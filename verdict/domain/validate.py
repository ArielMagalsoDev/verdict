"""Required-field validation and normalization — ordinary code, not an LLM.
Port of lib/validate.ts."""

from datetime import UTC, datetime

from .text import is_valid_email, normalize_domain, normalize_email

REQUIRED_STRING_FIELDS = (
    "submission_id",
    "first_name",
    "last_name",
    "work_email",
    "company_name",
    "message",
)

MESSAGE_MAX_LENGTH = 500
VALID_SOURCES = ("website", "event", "referral", "partner")


class ValidationError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__(f"validation failed: {'; '.join(errors)}")
        self.errors = errors


def validate_lead(raw: dict) -> tuple[dict, str, str | None]:
    """Returns (normalized_lead, email_normalized, website_normalized) or
    raises ValidationError."""
    if not isinstance(raw, dict):
        raise ValidationError(["payload is not an object"])

    errors: list[str] = []
    for field in REQUIRED_STRING_FIELDS:
        value = raw.get(field)
        if not isinstance(value, str) or value.strip() == "":
            errors.append(f"missing required field: {field}")

    work_email = raw.get("work_email")
    if isinstance(work_email, str) and not is_valid_email(work_email):
        errors.append("work_email is not a valid email address")

    message = raw.get("message")
    if isinstance(message, str) and len(message.strip()) > MESSAGE_MAX_LENGTH:
        errors.append(f"message must be {MESSAGE_MAX_LENGTH} characters or fewer")

    consent = raw.get("consent_to_contact")
    if consent is not True and consent is not False:
        errors.append("consent_to_contact must be a boolean")

    source = raw.get("source")
    if not isinstance(source, str) or source not in VALID_SOURCES:
        errors.append(f"source must be one of: {', '.join(VALID_SOURCES)}")

    if errors:
        raise ValidationError(errors)

    website = (raw.get("website") or "").strip() or None
    normalized = {
        "submission_id": raw["submission_id"].strip(),
        "source": source,
        "first_name": raw["first_name"].strip(),
        "last_name": raw["last_name"].strip(),
        "work_email": raw["work_email"].strip(),
        "company_name": raw["company_name"].strip(),
        "website": website,
        "job_title": (raw.get("job_title") or "").strip() or None,
        "country": (raw.get("country") or "").strip() or None,
        "message": raw["message"].strip(),
        "consent_to_contact": consent,
        "submitted_at": raw.get("submitted_at") or datetime.now(UTC).isoformat(),
    }

    return (
        normalized,
        normalize_email(normalized["work_email"]),
        normalize_domain(website) if website else None,
    )
