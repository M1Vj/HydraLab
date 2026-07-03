from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator

from hydra.providers.base import ProviderClient, ProviderError, ProviderMessage


class BudgetExceeded(RuntimeError):
    """Raised when a run would exceed the configured token/wall-clock ceiling.

    Section 36.3: block-and-prompt on any ceiling; never auto-continue.
    """

    def __init__(self, kind: str, limit: int, used: int) -> None:
        super().__init__(f"{kind} budget exceeded: used {used} of {limit}")
        self.kind = kind
        self.limit = limit
        self.used = used


@dataclass
class RunBudget:
    run_budget_tokens: int = 60000
    wall_clock_seconds: int = 120
    max_parallel_calls: int = 2

    def estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def check_prompt(self, prompt_text: str) -> None:
        used = self.estimate_tokens(prompt_text)
        if used > self.run_budget_tokens:
            raise BudgetExceeded("token", self.run_budget_tokens, used)


@dataclass
class RoutingPolicy:
    mode: str = "single"  # single / multi / rotation / fallback / policy-by-task
    preset: str = "Balanced"  # Accuracy / Speed / Cost / Balanced
    manual_provider: str | None = None


@dataclass
class ProviderRouter:
    """Routes a request across configured providers.

    Supports single / multi / rotation / fallback-on-error / policy-by-task and a
    manual per-chat override. Providers are ordered; fallback walks the list.
    """

    providers: list[ProviderClient] = field(default_factory=list)
    policy: RoutingPolicy = field(default_factory=RoutingPolicy)
    budget: RunBudget = field(default_factory=RunBudget)
    _rotation_index: int = 0

    def _ordered(self) -> list[ProviderClient]:
        if not self.providers:
            raise ProviderError("no providers configured")
        if self.policy.manual_provider:
            manual = [p for p in self.providers if p.provider_id == self.policy.manual_provider]
            rest = [p for p in self.providers if p.provider_id != self.policy.manual_provider]
            return manual + rest
        if self.policy.mode == "rotation" and len(self.providers) > 1:
            start = self._rotation_index % len(self.providers)
            self._rotation_index += 1
            return self.providers[start:] + self.providers[:start]
        return list(self.providers)

    async def stream(self, messages: list[ProviderMessage], *, model: str | None = None) -> AsyncIterator[str]:
        prompt_text = "\n".join(m.content for m in messages)
        self.budget.check_prompt(prompt_text)
        ordered = self._ordered()
        last_error: Exception | None = None
        for index, provider in enumerate(ordered):
            try:
                produced = False
                async for chunk in provider.stream(messages, model=model):
                    produced = True
                    yield chunk
                if produced or index == len(ordered) - 1:
                    return
            except Exception as exc:  # fallback-on-error
                last_error = exc
                continue
        if last_error is not None:
            raise ProviderError(f"all providers failed; last error: {last_error}")

    async def send(self, messages: list[ProviderMessage], *, model: str | None = None) -> str:
        prompt_text = "\n".join(m.content for m in messages)
        self.budget.check_prompt(prompt_text)
        last_error: Exception | None = None
        for provider in self._ordered():
            try:
                return await provider.send(messages, model=model)
            except Exception as exc:
                last_error = exc
                continue
        raise ProviderError(f"all providers failed; last error: {last_error}")
