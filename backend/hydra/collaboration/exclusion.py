"""Pre-serialization collaboration sync exclusion filter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

PROTECTED_CONTEXT_NAMES = {"SOUL.md", "USER.md", "MEMORY.md", "HYDRA.md"}
ALLOWED_PREFIXES = ("notes/", "writing/manuscripts/")
SECRET_MARKERS = (
    "api_key",
    "apikey",
    "provider token",
    "secret",
    "token",
    "password",
    "sk-",
    "ghp_",
    "github_pat_",
    "xoxb-",
    "xoxp-",
    "AKIA",
    "ASIA",
)


@dataclass(frozen=True)
class DocumentCandidate:
    path: str
    document_type: str
    content: str


@dataclass(frozen=True)
class ExclusionDecision:
    allowed: bool
    reason: str = ""


class SyncExclusionFilter:
    """Hard allowlist enforced before payload serialization."""

    def decide(self, candidate: DocumentCandidate) -> ExclusionDecision:
        path = _normalize(candidate.path)
        name = PurePosixPath(path).name
        lower_path = path.lower()
        lower_content = candidate.content.lower()
        if lower_path.startswith(".hydralab/") or "/.hydralab/" in lower_path:
            return ExclusionDecision(False, ".hydralab private cache")
        if lower_path.startswith("outputs/") or "/outputs/" in lower_path:
            return ExclusionDecision(False, "outputs are not collaborative targets")
        if name in PROTECTED_CONTEXT_NAMES:
            return ExclusionDecision(False, "protected context file")
        if lower_path.endswith(".log") or "/logs/" in lower_path or lower_path.startswith("logs/"):
            return ExclusionDecision(False, "local-only log")
        if not path.startswith(ALLOWED_PREFIXES):
            return ExclusionDecision(False, "outside collaboration allowlist")
        if any(marker.lower() in lower_path or marker.lower() in lower_content for marker in SECRET_MARKERS):
            return ExclusionDecision(False, "secret-like content")
        if candidate.document_type not in {"note", "markdown-draft"}:
            return ExclusionDecision(False, "unsupported document type")
        return ExclusionDecision(True)

    def serialize(self, candidate: DocumentCandidate) -> bytes | None:
        if not self.decide(candidate).allowed:
            return None
        return candidate.content.encode("utf-8")


def _normalize(path: str) -> str:
    normalized = path.replace("\\", "/").lstrip("/")
    parts = []
    for part in normalized.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            return "__blocked__/traversal"
        parts.append(part)
    return "/".join(parts)

