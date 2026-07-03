from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol, runtime_checkable


@dataclass
class ProviderMessage:
    role: str  # system / user / assistant
    content: str


@dataclass
class AuthStatus:
    ok: bool
    detail: str = ""
    scopes: list[str] = field(default_factory=list)


class ProviderError(RuntimeError):
    """Raised by adapters on transport/auth failure so the router can fall back."""


@runtime_checkable
class ProviderClient(Protocol):
    """HydraLab-owned provider contract. Adapters wrap a BYO-key HTTP transport.

    No third-party OAuth quota borrowing: OpenAI uses an API-key path only
    ([NEEDS CLARIFICATION]: no legally-usable third-party Codex OAuth flow exists,
    so the API-key path ships), OpenRouter uses a BYO-key API-key path.
    """

    provider_id: str
    model: str

    async def verify_auth(self) -> AuthStatus: ...

    async def stream(self, messages: list[ProviderMessage], *, model: str | None = None) -> AsyncIterator[str]: ...

    async def send(self, messages: list[ProviderMessage], *, model: str | None = None) -> str: ...

    def list_models(self) -> list[str]: ...
