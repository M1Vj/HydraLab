from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConsentDecision:
    allowed: bool
    reason: str
    status: str = "blocked"


@dataclass
class G1IndexingGate:
    local_research_indexing: str = "on"
    high_risk_indexing: str = "ask"


@dataclass
class G2BrowserGate:
    local_browser_capture: bool = False


@dataclass
class G3ProviderGate:
    provider_send: bool = False
    conservative_allowlist: set[str] = field(default_factory=lambda: {"active_file", "selection", "explicit_attachment"})
    opt_in_matrix: dict[str, bool] = field(
        default_factory=lambda: {
            "full_notes_corpus": False,
            "all_pdfs_extracted_text": False,
            "saved_chats": False,
            "agent_run_logs": False,
            "project_metadata": False,
            "browser_page_text": False,
        }
    )


@dataclass
class ConsentGates:
    g1: G1IndexingGate
    g2: G2BrowserGate
    g3: G3ProviderGate
    offline_only: bool = False

    @classmethod
    def defaults(cls) -> "ConsentGates":
        return cls(g1=G1IndexingGate(), g2=G2BrowserGate(), g3=G3ProviderGate())

    def can_send_to_provider(self, content_types: list[str]) -> ConsentDecision:
        if self.offline_only:
            return ConsentDecision(False, "Provider sends are blocked by offline-only mode.", "offline-locked")
        if not self.g3.provider_send:
            return ConsentDecision(False, "Provider send gate G3 is not granted.")

        for content_type in content_types:
            if content_type in self.g3.conservative_allowlist:
                continue
            if not self.g3.opt_in_matrix.get(content_type, False):
                return ConsentDecision(False, f"{content_type} is not opted in for provider send.")
        return ConsentDecision(True, "Allowed by G3 provider-send policy.", "allowed")
