from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from hydra.providers.base import AuthStatus, ProviderError, ProviderMessage


class OpenAIProvider:
    """OpenAI adapter, API-key path only.

    Third-party ChatGPT-quota OAuth does not exist for external apps, so HydraLab
    ships the BYO API-key path (see base.ProviderClient docstring).
    """

    provider_id = "openai"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4.1-mini",
        *,
        base_url: str = "https://api.openai.com/v1",
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
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def verify_auth(self) -> AuthStatus:
        client = self._make_client()
        try:
            response = await client.get(f"{self.base_url}/models", headers=self._headers)
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
                    raise ProviderError(f"openai stream failed: {response.status_code} {body.decode('utf-8', 'ignore')}")
                async for line in response.aiter_lines():
                    piece = _parse_sse_delta(line)
                    if piece:
                        yield piece
        except httpx.HTTPError as exc:
            raise ProviderError(f"openai transport error: {exc}") from exc
        finally:
            if self._owns_client:
                await client.aclose()

    async def send(self, messages: list[ProviderMessage], *, model: str | None = None) -> str:
        parts = [chunk async for chunk in self.stream(messages, model=model)]
        return "".join(parts)

    def list_models(self) -> list[str]:
        return [self.model]


def _parse_sse_delta(line: str) -> str:
    line = line.strip()
    if not line.startswith("data:"):
        return ""
    data = line[len("data:") :].strip()
    if not data or data == "[DONE]":
        return ""
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        return ""
    choices = parsed.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    return str(delta.get("content") or "")
