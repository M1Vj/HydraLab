from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from hydra.settings.toml_config import default_settings, load_settings, save_settings


class SecretStore(Protocol):
    def set_password(self, service: str, username: str, password: str) -> None: ...
    def get_password(self, service: str, username: str) -> str | None: ...
    def delete_password(self, service: str, username: str) -> None: ...


class KeyringSecretStore:
    def __init__(self, service_prefix: str = "HydraLab") -> None:
        import keyring

        self._keyring = keyring
        self.service_prefix = service_prefix

    def set_password(self, service: str, username: str, password: str) -> None:
        self._keyring.set_password(f"{self.service_prefix}:{service}", username, password)

    def get_password(self, service: str, username: str) -> str | None:
        return self._keyring.get_password(f"{self.service_prefix}:{service}", username)

    def delete_password(self, service: str, username: str) -> None:
        self._keyring.delete_password(f"{self.service_prefix}:{service}", username)


@dataclass
class InMemorySecretStore:
    values: dict[tuple[str, str], str] = field(default_factory=dict)

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


class ProviderSecretService:
    def __init__(self, store: SecretStore) -> None:
        self.store = store

    def _ref(self, provider_id: str, secret_name: str = "api_key") -> str:
        return f"keychain:hydralab/{provider_id}" if secret_name == "api_key" else f"keychain:hydralab/{provider_id}/{secret_name}"

    def save_provider_secret(self, settings_path: Path, provider_id: str, secret_name: str, secret_value: str) -> dict:
        settings_path = Path(settings_path)
        if settings_path.exists():
            settings = load_settings(settings_path).data
        else:
            settings = default_settings()

        service = f"hydralab/{provider_id}"
        self.store.set_password(service, secret_name, secret_value)
        secret_ref = self._ref(provider_id, secret_name)

        providers = settings.setdefault("providers", {})
        accounts = providers.setdefault("accounts", {})
        account = accounts.setdefault(provider_id, {"provider_id": provider_id})
        account["secret_ref"] = secret_ref
        account["auth_method"] = account.get("auth_method", "api_key")
        account["credential_kind"] = secret_name
        save_settings(settings_path, settings)
        return settings

    def get_provider_secret(self, settings_path: Path, provider_id: str, secret_name: str) -> str | None:
        settings = load_settings(settings_path).data
        account = settings.get("providers", {}).get("accounts", {}).get(provider_id, {})
        if account.get("secret_ref") != self._ref(provider_id, secret_name):
            return None
        return self.store.get_password(f"hydralab/{provider_id}", secret_name)

    def has_provider_secret(self, provider_id: str, secret_name: str = "api_key") -> bool:
        return self.store.get_password(f"hydralab/{provider_id}", secret_name) is not None
