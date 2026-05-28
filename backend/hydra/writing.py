from __future__ import annotations

import re


ABSOLUTE_TERMS = ("always", "never", "proves", "guarantees", "best", "all studies")


def analyze_text(text: str) -> dict[str, object]:
    unsupported = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if _needs_support(sentence)]
    rewrite = _rewrite(text)
    
    categories = []
    if unsupported:
        categories.append("unsupported claim")
        categories.append("missing-citation")
    
    if len(text.split()) < 40:
        categories.append("clarity")
        categories.append("coherence")
        
    if "!" in text or text.isupper():
        categories.append("tone")

    if not categories:
        categories.append("clarity") # Add a default if nothing else

    critique = []
    if "unsupported claim" in categories:
        critique.append("Several claims use absolute wording and need direct evidence.")
    if "clarity" in categories and len(text.split()) < 40:
        critique.append("Argument is brief; add context, evidence, and limitation language.")
    if not critique:
        critique.append("Draft is readable; next pass should verify citations and tighten transitions.")

    return {
        "rewrite": rewrite, 
        "critique": critique, 
        "unsupported_claims": unsupported,
        "categories": categories
    }

def review_text(text: str) -> dict[str, object]:
    return analyze_text(text)


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
