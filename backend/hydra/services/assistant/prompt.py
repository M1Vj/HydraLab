from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hydra.providers.base import ProviderMessage

# Compact core prompt (Section 20 / HL-ASSIST-07): NOT a monolithic mega-prompt.
CORE_PROMPT = (
    "You are HydraLab's Passive research assistant. You summarize, explain, and suggest. "
    "You never take autonomous actions; every substantive output is a suggestion the "
    "researcher must accept. Ground answers in provided project context only."
)


@dataclass
class InstructionLayer:
    core_prompt: str
    skill_descriptors: list[dict[str, Any]] = field(default_factory=list)
    user_request: str = ""
    trusted_context: list[str] = field(default_factory=list)
    untrusted_region: dict[str, Any] | None = None

    def descriptor_ids(self) -> list[str]:
        return [str(d.get("id")) for d in self.skill_descriptors]

    def to_messages(self) -> list[ProviderMessage]:
        segments: list[ProviderMessage] = [ProviderMessage(role="system", content=self.core_prompt)]
        for descriptor in self.skill_descriptors:
            segments.append(
                ProviderMessage(
                    role="system",
                    content=f"[skill:{descriptor.get('id')}] {descriptor.get('name')} — {descriptor.get('description')}",
                )
            )
        for block in self.trusted_context:
            segments.append(ProviderMessage(role="system", content=f"[trusted-context]\n{block}"))
        if self.untrusted_region:
            segments.append(ProviderMessage(role="user", content=self.untrusted_region["text"]))
        segments.append(ProviderMessage(role="user", content=self.user_request))
        return segments


def assemble_instruction_layer(
    user_request: str,
    *,
    enabled_skill_descriptors: list[dict[str, Any]] | None = None,
    trusted_context: list[str] | None = None,
    untrusted_region: dict[str, Any] | None = None,
    core_prompt: str = CORE_PROMPT,
) -> InstructionLayer:
    """Build the trusted instruction layer from core prompt + enabled skills + request.

    Disabled skills are excluded by construction (caller passes only enabled ones).
    Untrusted content never enters the instruction/system layer — it rides in its own
    delimited region as a user-role reference block.
    """
    return InstructionLayer(
        core_prompt=core_prompt,
        skill_descriptors=list(enabled_skill_descriptors or []),
        user_request=user_request,
        trusted_context=list(trusted_context or []),
        untrusted_region=untrusted_region,
    )
