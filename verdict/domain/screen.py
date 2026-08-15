"""Deterministic, zero-cost fast-path screen over RESEARCHED content (not
user input — Verdict's injection surface is retrieved web pages). Port of
lib/screen.ts. Advisory, not a blocker: it flags a source for the audit
trail. The real defense is structural — the extraction tool's field enum and
domain/verify.py's grounding check — this is defense-in-depth on top of that."""

import re

SUSPICIOUS_PATTERNS = [
    re.compile(r"ignore (all|any|previous|prior) instructions?", re.I),
    re.compile(r"system (notice|override|directive|prompt)", re.I),
    re.compile(r"you are now", re.I),
    re.compile(r"disregard (the )?(above|prior)", re.I),
    re.compile(r"do not mention this", re.I),
    re.compile(r"pre-?approved", re.I),
    re.compile(r"set (the )?(qualification )?score to", re.I),
]


def screen_source_text(text: str) -> dict:
    matched = [p.pattern for p in SUSPICIOUS_PATTERNS if p.search(text)]
    return {"flagged": len(matched) > 0, "matched_patterns": matched}
