"""Secret / private-content redaction (branch 03-05, HL-TRUST-22).

Secrets, provider keys and private research content are excluded from fixer
prompts, diffs, logs and audit entries. Secrets are sourced only from the OS
credential store by reference and never inlined; if a raw key ever appears in a
candidate diff it is replaced with a fixed placeholder before anything is
persisted. Mirrors the backend ``RAW_SECRET_PREFIXES`` set so the detector stays
consistent with the app-wide secret-reference gate.
"""

from __future__ import annotations

import re

REDACTED = "[REDACTED]"

# Canonical raw-secret prefixes (mirrors hydra.app.RAW_SECRET_PREFIXES and the
# frontend settingsController.RAW_SECRET_PREFIXES). A keychain:*/env:* reference
# is NOT a raw secret and is intentionally not matched.
RAW_SECRET_PREFIXES: tuple[str, ...] = (
    "sk-",
    "ai-",
    "ghp_",
    "github_pat_",
    "xoxb-",
    "xoxp-",
    "AKIA",
    "ASIA",
)

# A raw-secret token: one of the known prefixes followed by key-ish characters.
_SECRET_TOKEN = re.compile(
    "(?:" + "|".join(re.escape(prefix) for prefix in RAW_SECRET_PREFIXES) + r")[A-Za-z0-9_\-]+"
)


def contains_secret(text: str) -> bool:
    """True when a raw-secret token is present in ``text``."""
    return bool(_SECRET_TOKEN.search(text or ""))


def redact(text: str) -> str:
    """Replace every raw-secret token with the fixed placeholder.

    Never emits partial/truncated key material: the entire token is replaced.
    """
    if not text:
        return text
    return _SECRET_TOKEN.sub(REDACTED, text)
