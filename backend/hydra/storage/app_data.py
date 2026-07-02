from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from hydra.settings.toml_config import default_settings, save_settings


@dataclass(frozen=True)
class AppDataProfile:
    app_root: Path
    profile_id: str
    profile_root: Path

    def path_for_profile(self, profile_id: str) -> Path:
        return self.app_root / "profiles" / profile_id


def app_data_root() -> Path:
    override = os.environ.get("HYDRALAB_APP_DATA_ROOT")
    if override:
        return Path(override).expanduser()
    hydra_home = os.environ.get("HYDRA_HOME")
    if hydra_home:
        return Path(hydra_home).expanduser() / "app-data"
    return Path.home() / "Library" / "Application Support" / "HydraLab"


def init_app_data(profile_id: str = "default") -> AppDataProfile:
    root = app_data_root()
    profile_root = root / "profiles" / profile_id
    profile_root.mkdir(parents=True, exist_ok=True)
    (root / "runtime").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)

    for filename in ("SOUL.md", "USER.md", "MEMORY.md"):
        path = profile_root / filename
        if not path.exists():
            path.write_text(f"# {filename.removesuffix('.md')}\n")

    settings_path = root / "settings.toml"
    if not settings_path.exists():
        save_settings(settings_path, default_settings())

    return AppDataProfile(app_root=root, profile_id=profile_id, profile_root=profile_root)
