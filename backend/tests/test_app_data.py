from pathlib import Path

from hydra.storage import app_data


def test_app_data_root_env_overrides_win_on_all_platforms(tmp_path, monkeypatch):
    override = tmp_path / "override"
    monkeypatch.setattr(app_data.sys, "platform", "win32")
    monkeypatch.setenv("HYDRALAB_APP_DATA_ROOT", str(override))
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path / "hydra-home"))

    assert app_data.app_data_root() == override


def test_app_data_root_hydra_home_wins_after_primary_override(tmp_path, monkeypatch):
    monkeypatch.setattr(app_data.sys, "platform", "linux")
    monkeypatch.delenv("HYDRALAB_APP_DATA_ROOT", raising=False)
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path / "hydra-home"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    assert app_data.app_data_root() == tmp_path / "hydra-home" / "app-data"


def test_app_data_root_windows_uses_appdata_or_roaming_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(app_data.sys, "platform", "win32")
    monkeypatch.delenv("HYDRALAB_APP_DATA_ROOT", raising=False)
    monkeypatch.delenv("HYDRA_HOME", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))

    assert app_data.app_data_root() == tmp_path / "AppData" / "Roaming" / "HydraLab"

    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert app_data.app_data_root() == tmp_path / "AppData" / "Roaming" / "HydraLab"


def test_app_data_root_linux_uses_xdg_or_local_share_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(app_data.sys, "platform", "linux")
    monkeypatch.delenv("HYDRALAB_APP_DATA_ROOT", raising=False)
    monkeypatch.delenv("HYDRA_HOME", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    assert app_data.app_data_root() == tmp_path / "xdg" / "HydraLab"

    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert app_data.app_data_root() == tmp_path / ".local" / "share" / "HydraLab"


def test_app_data_root_macos_default_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(app_data.sys, "platform", "darwin")
    monkeypatch.delenv("HYDRALAB_APP_DATA_ROOT", raising=False)
    monkeypatch.delenv("HYDRA_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert app_data.app_data_root() == tmp_path / "Library" / "Application Support" / "HydraLab"
