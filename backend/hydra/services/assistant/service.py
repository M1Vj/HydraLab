from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from hydra.providers.base import ProviderClient, ProviderMessage
from hydra.providers.mock import MockProvider
from hydra.providers.routing import BudgetExceeded, ProviderRouter, RoutingPolicy, RunBudget
from hydra.services.assistant.consent import (
    HardBlockedError,
    ResolvedScope,
    SendScopeItem,
    resolve_send_scope,
)
from hydra.services.assistant.prompt import assemble_instruction_layer
from hydra.services.assistant.untrusted import assemble_untrusted_region

UNTRUSTED_REF_TYPES = {"pdf", "browser", "browser_event", "source", "note"}


@dataclass
class ProviderCache:
    """Tiny provider-response cache; purged when offline-only engages (HL-CONSENT-03)."""

    entries: dict[str, str] = field(default_factory=dict)

    def purge(self) -> None:
        self.entries.clear()


@dataclass
class AssistantConfig:
    g3_enabled: bool = False
    offline_only: bool = False
    opt_ins: dict[str, bool] = field(default_factory=dict)
    ignored_paths: list[str] = field(default_factory=list)
    default_mode: str = "passive"
    run_budget: int = 60000
    wall_clock_seconds: int = 120
    max_parallel_calls: int = 2


class AssistantService:
    def __init__(
        self,
        *,
        router: ProviderRouter | None = None,
        config: AssistantConfig | None = None,
        cache: ProviderCache | None = None,
        skill_descriptors: list[dict[str, Any]] | None = None,
    ) -> None:
        self.config = config or AssistantConfig()
        self.cache = cache or ProviderCache()
        self.skill_descriptors = skill_descriptors or []
        self.router = router or ProviderRouter(
            providers=[MockProvider()],
            policy=RoutingPolicy(mode="single"),
            budget=RunBudget(
                run_budget_tokens=self.config.run_budget,
                wall_clock_seconds=self.config.wall_clock_seconds,
                max_parallel_calls=self.config.max_parallel_calls,
            ),
        )

    # ------------------------------------------------------------------ consent
    def resolve_scope(self, context_refs: list[dict[str, Any]]) -> ResolvedScope:
        items = [
            SendScopeItem(
                ref_type=str(ref.get("type") or "attachment"),
                id_or_path=str(ref.get("id_or_path") or ref.get("id") or ""),
                locator=dict(ref.get("locator") or {}),
                label=str(ref.get("label") or ""),
            )
            for ref in context_refs
        ]
        return resolve_send_scope(
            items,
            g3_enabled=self.config.g3_enabled,
            offline_only=self.config.offline_only,
            opt_ins=self.config.opt_ins,
            ignored_paths=self.config.ignored_paths,
        )

    def _build_messages(self, user_message: str, scope: ResolvedScope, context_refs: list[dict[str, Any]]) -> list[ProviderMessage]:
        trusted_blocks: list[str] = []
        untrusted_text_parts: list[str] = []
        included_ids = {(item["type"], item["id_or_path"]) for item in scope.included}
        for ref in context_refs:
            key = (str(ref.get("type") or "attachment"), str(ref.get("id_or_path") or ref.get("id") or ""))
            if key not in included_ids:
                continue
            text = str(ref.get("text") or ref.get("content") or "")
            if not text:
                continue
            if key[0] in UNTRUSTED_REF_TYPES:
                untrusted_text_parts.append(text)
            else:
                trusted_blocks.append(text)
        untrusted_region = assemble_untrusted_region("\n\n".join(untrusted_text_parts)) if untrusted_text_parts else None
        layer = assemble_instruction_layer(
            user_message,
            enabled_skill_descriptors=self.skill_descriptors,
            trusted_context=trusted_blocks,
            untrusted_region=untrusted_region,
        )
        return layer.to_messages()

    # ------------------------------------------------------------------- stream
    async def stream_reply(
        self,
        user_message: str,
        *,
        context_refs: Optional[list[dict[str, Any]]] = None,
        on_delta=None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield SSE-shaped events. ``on_delta`` (async) persists each streamed prefix."""
        context_refs = context_refs or []
        if self.config.offline_only:
            self.cache.purge()
            yield {"type": "blocked", "reason": "offline-only mode blocks all provider sends", "status": "offline-blocked"}
            return

        scope = self.resolve_scope(context_refs)
        if scope.has_hard_block:
            yield {
                "type": "blocked",
                "reason": scope.blocked[0]["reason"],
                "status": "hard-blocked",
                "blocked": scope.blocked,
            }
            return

        yield {"type": "status", "content": "assembling context...", "included": scope.included, "excluded": scope.excluded}
        messages = self._build_messages(user_message, scope, context_refs)
        try:
            async for chunk in self.router.stream(messages):
                if on_delta is not None:
                    await on_delta(chunk)
                yield {"type": "message", "content": chunk}
        except BudgetExceeded as exc:
            yield {"type": "budget", "reason": str(exc), "status": "budget-exceeded", "kind": exc.kind}
            return
        except Exception as exc:  # provider failure surfaced, not silently retried elsewhere
            yield {"type": "error", "reason": str(exc)}
            return
        yield {"type": "done"}
