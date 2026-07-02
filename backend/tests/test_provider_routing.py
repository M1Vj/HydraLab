import json

import httpx
import pytest

from hydra.providers import (
    BudgetExceeded,
    MockProvider,
    OpenAIProvider,
    OpenRouterProvider,
    ProviderRouter,
    RoutingPolicy,
    RunBudget,
)
from hydra.providers.base import ProviderMessage


def _sse_stream_transport():
    """A mock transport that returns an OpenAI-style SSE chat completion stream."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models") or request.url.path.endswith("/auth/key"):
            return httpx.Response(200, json={"ok": True})
        chunks = [
            'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n',
            'data: {"choices":[{"delta":{"content":" world"}}]}\n\n',
            "data: [DONE]\n\n",
        ]
        return httpx.Response(200, text="".join(chunks), headers={"content-type": "text/event-stream"})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_hl_consent_07_openai_adapter_verify_and_stream():
    client = httpx.AsyncClient(transport=_sse_stream_transport())
    provider = OpenAIProvider(api_key="sk-test", model="gpt-4.1-mini", client=client)
    auth = await provider.verify_auth()
    assert auth.ok is True
    chunks = [c async for c in provider.stream([ProviderMessage("user", "hi")])]
    assert "".join(chunks) == "Hello world"
    await client.aclose()


@pytest.mark.asyncio
async def test_hl_consent_07_openrouter_adapter_verify_and_stream():
    client = httpx.AsyncClient(transport=_sse_stream_transport())
    provider = OpenRouterProvider(api_key="sk-or", model="openrouter/auto", client=client)
    auth = await provider.verify_auth()
    assert auth.ok is True
    text = await provider.send([ProviderMessage("user", "hi")])
    assert text == "Hello world"
    await client.aclose()


@pytest.mark.asyncio
async def test_hl_consent_07_router_falls_back_on_primary_error():
    primary = MockProvider(provider_id="openai", fail=True)
    secondary = MockProvider(provider_id="openrouter")
    router = ProviderRouter(providers=[primary, secondary], policy=RoutingPolicy(mode="fallback"))
    text = await router.send([ProviderMessage("user", "hello there")])
    assert "hello there" in text
    assert secondary.calls == 1


@pytest.mark.asyncio
async def test_hl_consent_07_manual_per_chat_selection_prefers_provider():
    a = MockProvider(provider_id="openai")
    b = MockProvider(provider_id="openrouter")
    router = ProviderRouter(providers=[a, b], policy=RoutingPolicy(mode="single", manual_provider="openrouter"))
    await router.send([ProviderMessage("user", "route me")])
    assert b.calls == 1
    assert a.calls == 0


@pytest.mark.asyncio
async def test_hl_consent_07_budget_block_and_prompt():
    router = ProviderRouter(providers=[MockProvider()], budget=RunBudget(run_budget_tokens=5))
    big_prompt = ProviderMessage("user", "x" * 400)  # ~100 tokens > 5
    with pytest.raises(BudgetExceeded) as excinfo:
        await router.send([big_prompt])
    assert excinfo.value.kind == "token"


@pytest.mark.asyncio
async def test_rotation_cycles_providers():
    a = MockProvider(provider_id="a")
    b = MockProvider(provider_id="b")
    router = ProviderRouter(providers=[a, b], policy=RoutingPolicy(mode="rotation"))
    order_first = router._ordered()[0].provider_id
    order_second = router._ordered()[0].provider_id
    assert {order_first, order_second} == {"a", "b"}
