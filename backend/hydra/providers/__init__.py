from hydra.providers.base import AuthStatus, ProviderClient, ProviderError, ProviderMessage
from hydra.providers.mock import MockProvider
from hydra.providers.openai_adapter import OpenAIProvider
from hydra.providers.openrouter_adapter import OpenRouterProvider
from hydra.providers.routing import BudgetExceeded, ProviderRouter, RoutingPolicy, RunBudget

__all__ = [
    "AuthStatus",
    "ProviderClient",
    "ProviderError",
    "ProviderMessage",
    "MockProvider",
    "OpenAIProvider",
    "OpenRouterProvider",
    "BudgetExceeded",
    "ProviderRouter",
    "RoutingPolicy",
    "RunBudget",
    "build_provider",
]


def build_provider(provider_id: str, api_key: str, model: str, **kwargs):
    """Factory mapping a provider id to its HydraLab adapter.

    Transport is injectable via kwargs (``client=``) so tests never hit live APIs.
    """
    if provider_id == "openai":
        return OpenAIProvider(api_key=api_key, model=model, **kwargs)
    if provider_id == "openrouter":
        return OpenRouterProvider(api_key=api_key, model=model, **kwargs)
    if provider_id == "mock":
        return MockProvider(model=model or "mock-1")
    raise ProviderError(f"unsupported provider: {provider_id}")
