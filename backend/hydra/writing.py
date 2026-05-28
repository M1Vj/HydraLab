from __future__ import annotations

import re


ABSOLUTE_TERMS = ("always", "never", "proves", "guarantees", "best", "all studies")


def review_text(text: str) -> dict[str, object]:
    unsupported = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if _needs_support(sentence)]
    rewrite = _rewrite(text)
    critique = []
    if unsupported:
        critique.append("Several claims use absolute wording and need direct evidence.")
    if len(text.split()) < 40:
        critique.append("Argument is brief; add context, evidence, and limitation language.")
    if not critique:
        critique.append("Draft is readable; next pass should verify citations and tighten transitions.")
    return {"rewrite": rewrite, "critique": critique, "unsupported_claims": unsupported}


def _needs_support(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(term in lowered for term in ABSOLUTE_TERMS)


def _rewrite(text: str) -> str:
    replacements = {
        "proves": "suggests",
        "always": "often",
        "never": "rarely",
        "best": "strong candidate",
        "very good": "promising",
        "guarantees": "may improve",
    }
    rewritten = text
    for old, new in replacements.items():
        rewritten = re.sub(rf"\b{re.escape(old)}\b", new, rewritten, flags=re.IGNORECASE)
    return rewritten
