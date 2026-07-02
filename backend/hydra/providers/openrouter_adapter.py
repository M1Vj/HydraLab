from __future__ import annotations

from typing import AsyncIterator

import httpx

from hydra.providers.base import AuthStatus, ProviderError, ProviderMessage
from hydra.providers.openai_adapter import _parse_sse_delta


class OpenRouterProvider:
    """OpenRouter adapter (BYO API key, OpenAI-compatible schema).

    OpenRouter also supports a real PKCE OAuth key-provisioning flow; HydraLab stores
    the resulting key in the OS credential store exactly like any BYO key.
    """

    provider_id = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str = "openrouter/auto",
        *,
        base_url: str = "https://openrouter.ai/api/v1",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client = client
        self._owns_client = client is None

    def _make_client(self) -> httpx.AsyncClient:
        return self._client or httpx.AsyncClient(timeout=httpx.Timeout(60.0))

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://hydralab.local",
            "X-Title": "HydraLab",
        }

    async def verify_auth(self) -> AuthStatus:
        client = self._make_client()
        try:
            response = await client.get(f"{self.base_url}/auth/key", headers=self._headers)
            if response.status_code == 200:
                return AuthStatus(ok=True, detail="authenticated", scopes=["chat.completions"])
            return AuthStatus(ok=False, detail=f"auth failed: {response.status_code}")
        except httpx.HTTPError as exc:
            return AuthStatus(ok=False, detail=f"transport error: {exc}")
        finally:
            if self._owns_client:
                await client.aclose()

    async def stream(self, messages: list[ProviderMessage], *, model: str | None = None) -> AsyncIterator[str]:
        payload = {
            "model": model or self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
        }
        client = self._make_client()
        try:
            async with client.stream("POST", f"{self.base_url}/chat/completions", headers=self._headers, json=payload) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise ProviderError(f"openrouter stream failed: {response.status_code} {body.decode('utf-8', 'ignore')}")
                async for line in response.aiter_lines():
                    piece = _parse_sse_delta(line)
                    if piece:
                        yield piece
        except httpx.HTTPError as exc:
            raise ProviderError(f"openrouter transport error: {exc}") from exc
        finally:
            if self._owns_client:
                await client.aclose()

    async def send(self, messages: list[ProviderMessage], *, model: str | None = None) -> str:
        parts = [chunk async for chunk in self.stream(messages, model=model)]
        return "".join(parts)

    def list_models(self) -> list[str]:
        return [self.model]
