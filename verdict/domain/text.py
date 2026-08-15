"""Pure string-normalization and similarity helpers — port of lib/text.ts.
No IO, fully unit-testable; identity resolution and validation are built on
this layer."""

import re


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_domain(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = re.sub(r"^www\.", "", value)
    value = re.sub(r"/.*$", "", value)
    return value


def email_domain(email: str) -> str | None:
    at = email.rfind("@")
    if at == -1:
        return None
    return normalize_domain(email[at + 1 :])


_COMPANY_SUFFIXES = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|pty|corp|corporation|co|group|grp|company)\b"
)


def normalize_company_name(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[.,]", "", name)
    name = _COMPANY_SUFFIXES.sub("", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def _tokenize(s: str) -> set[str]:
    return {t for t in s.split() if t}


def name_similarity(a: str, b: str) -> float:
    """Jaccard similarity over word tokens, 0..1. Deterministic, dependency-free."""
    ta = _tokenize(normalize_company_name(a))
    tb = _tokenize(normalize_company_name(b))
    if not ta or not tb:
        return 0.0
    intersection = len(ta & tb)
    union = len(ta) + len(tb) - intersection
    return 0.0 if union == 0 else intersection / union


def is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email.strip()))
