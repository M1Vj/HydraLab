"""Reproducibility redaction filter over the clean-export baseline (HL-QUAL-34)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hydra.services.export.bundle import ExportOptions, SECRET_TOKEN_PREFIXES, scrub_secret_text, should_exclude

KEYCHAIN_REF_RE = re.compile(r"\b(keychain|security|credential-store)://[^\s]+", re.IGNORECASE)


@dataclass(frozen=True)
class RedactionDecision:
    id: str
    category: str
    path_or_ref: str
    reason: str
    decision: str = "exclude"

    def public_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "category": self.category,
            "path_or_ref": self.path_or_ref,
            "reason": self.reason,
            "decision": self.decision,
        }


class ReproducibilityRedactionFilter:
    def __init__(self, project_root: Path, *, include_private_chats: bool = False) -> None:
        self.project_root = Path(project_root)
        self.options = ExportOptions(include_chats=include_private_chats)

    def scan_paths(self, relative_paths: list[str]) -> list[RedactionDecision]:
        decisions: list[RedactionDecision] = []
        for relpath in sorted(dict.fromkeys(relative_paths)):
            decision = self.decision_for_path(relpath)
            if decision is not None:
                decisions.append(decision)
        return decisions

    def decision_for_path(self, relative_path: str) -> RedactionDecision | None:
        normalized = _normalize(relative_path)
        category, reason = self._classify_path(normalized)
        if category is not None:
            return _decision(category, normalized, reason)
        if should_exclude(normalized, self.options):
            return _decision("excluded-by-default", normalized, "path is excluded by the clean export baseline")
        absolute = self.project_root / normalized
        if absolute.is_file():
            try:
                sample = absolute.read_text(encoding="utf-8", errors="ignore")[:200_000]
            except OSError:
                sample = ""
            content_decision = self.decision_for_text(sample, path_or_ref=normalized)
            if content_decision is not None:
                return content_decision
        return None

    def decision_for_text(self, text: str, *, path_or_ref: str) -> RedactionDecision | None:
        if KEYCHAIN_REF_RE.search(text):
            return _decision("credentials", path_or_ref, "OS credential-store reference is hard-blocked")
        for prefix in SECRET_TOKEN_PREFIXES:
            if any(token.startswith(prefix) and len(token) > 8 for token in text.split()):
                return _decision("secrets", path_or_ref, "content contains a provider/API secret-shaped token")
        return None

    def scrub_text(self, text: str) -> str:
        return scrub_secret_text(KEYCHAIN_REF_RE.sub("[REDACTED-CREDENTIAL-REF]", text))

    def refuse_hard_blocked(self, path_or_ref: str) -> RedactionDecision:
        normalized = _normalize(path_or_ref)
        category, reason = self._classify_path(normalized)
        if category is None:
            category = "hard-blocked"
            reason = "requested item is not eligible for reproducibility export"
        return _decision(category, normalized, f"Refused hard-blocked item {normalized}: {reason}", decision="refuse")

    def is_hard_blocked(self, relative_path: str) -> bool:
        category, _reason = self._classify_path(_normalize(relative_path))
        return category in {"secrets", "credentials", "provider-cache", "git-internals", "hydralab-internals"}

    def _classify_path(self, relative_path: str) -> tuple[str | None, str | None]:
        path = Path(relative_path)
        parts = path.parts
        if not parts:
            return "excluded-by-default", "empty path is not exportable"
        posix = "/".join(parts)
        lower_name = parts[-1].lower()
        if parts[0] == ".git":
            return "git-internals", ".git internals are hard-blocked"
        if parts[0] == ".hydralab" and len(parts) > 2 and parts[1] == "cache" and parts[2] == "provider":
            return "provider-cache", ".hydralab/cache/provider content is hard-blocked"
        if parts[0] == ".hydralab" and len(parts) > 1 and parts[1] in {"cache", "temp", "logs", "runtime", "indexes"}:
            return "hydralab-internals", ".hydralab cache/temp/log/runtime/index data is hard-blocked"
        if parts[0] == ".hydralab" and len(parts) > 1 and parts[1] == "credentials":
            return "credentials", "OS credential-store material is hard-blocked"
        if lower_name == ".netrc" or "/.credentials/" in f"/{posix}/":
            return "credentials", "credential-store material is hard-blocked"
        if lower_name.startswith(".env") or lower_name in {"credentials", "secrets"}:
            return "secrets", "secret-bearing file is hard-blocked"
        if lower_name.endswith((".pem", ".key", ".p12", ".pfx")):
            return "secrets", "key material is hard-blocked"
        if posix == "work/chats" or posix.startswith("work/chats/"):
            return "private-chats", "private chats are excluded unless explicitly opted in"
        return None, None


def _normalize(value: str) -> str:
    return Path(value).as_posix().lstrip("/")


def _decision(category: str, path_or_ref: str, reason: str | None, *, decision: str = "exclude") -> RedactionDecision:
    digest = hashlib.sha256(f"{category}:{path_or_ref}".encode("utf-8")).hexdigest()[:12]
    return RedactionDecision(
        id=f"redact-{digest}",
        category=category,
        path_or_ref=path_or_ref,
        reason=reason or "excluded",
        decision=decision,
    )
