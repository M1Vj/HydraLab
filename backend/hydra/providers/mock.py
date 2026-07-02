from __future__ import annotations

from typing import AsyncIterator

from hydra.providers.base import AuthStatus, ProviderMessage


class MockProvider:
    """Deterministic local echo provider for tests and default dev posture.

    This is NOT a local model and never runs when offline-only is engaged; it is a
    transport-free stand-in so tests never hit a live LLM API.
    """

    def __init__(self, provider_id: str = "mock", model: str = "mock-1", *, fail: bool = False) -> None:
        self.provider_id = provider_id
        self.model = model
        self._fail = fail
        self.calls = 0

    async def verify_auth(self) -> AuthStatus:
        if self._fail:
            return AuthStatus(ok=False, detail="mock auth failure")
        return AuthStatus(ok=True, detail="mock ok", scopes=["chat"])

    def _answer(self, messages: list[ProviderMessage]) -> str:
        user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return f"Passive assistant suggestion for: {user.strip()}".strip()

    async def stream(self, messages: list[ProviderMessage], *, model: str | None = None) -> AsyncIterator[str]:
        self.calls += 1
        if self._fail:
            raise RuntimeError("mock provider stream failure")
        for word in self._answer(messages).split(" "):
            yield word + " "

    async def send(self, messages: list[ProviderMessage], *, model: str | None = None) -> str:
        self.calls += 1
        if self._fail:
            raise RuntimeError("mock provider send failure")
        return self._answer(messages)

    def list_models(self) -> list[str]:
        return [self.model]
