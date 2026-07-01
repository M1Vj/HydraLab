from __future__ import annotations

from dataclasses import dataclass


ALWAYS_EXCLUDED = {
    ".git",
    "credential-files",
    "secrets",
    ".env",
    "cache",
    "temp",
    ".hydralab-cache",
    ".hydralab-temp",
}
DEFAULT_INDEXED = {"sources", "knowledge", "work", "writing", "outputs"}
CONSENT_REQUIRED = {"code-folder", "browser-history", "browser-artifacts", "chat-logs", "agent-memory", "large-generated"}


@dataclass(frozen=True)
class IndexingPolicyDecision:
    status: str
    reason: str


def resolve_indexing_policy(category: str) -> IndexingPolicyDecision:
    if category in ALWAYS_EXCLUDED:
        return IndexingPolicyDecision("excluded", "Always excluded from indexing.")
    if category in CONSENT_REQUIRED:
        return IndexingPolicyDecision("needs-consent", "High-risk or high-noise content requires G1 consent.")
    if category in DEFAULT_INDEXED:
        return IndexingPolicyDecision("indexed", "Normal research folder indexed by default.")
    return IndexingPolicyDecision("needs-consent", "Unknown categories require explicit indexing consent.")
