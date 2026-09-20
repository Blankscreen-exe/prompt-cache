from __future__ import annotations

from pathlib import Path

import pytest

from prompt_cache import paths


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (paths.DATA_DIR_ENV, "APPDATA", "XDG_DATA_HOME"):
        monkeypatch.delenv(name, raising=False)


def test_env_override_wins_on_every_platform(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv(paths.DATA_DIR_ENV, str(tmp_path / "elsewhere"))
    for platform in ("win32", "linux"):
        monkeypatch.setattr(paths.sys, "platform", platform)
        assert paths.data_dir() == tmp_path / "elsewhere"


def test_env_override_expands_user(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(paths.DATA_DIR_ENV, "~/pc-data")
    assert paths.data_dir() == Path.home() / "pc-data"


def test_windows_uses_appdata(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", r"C:\Users\someone\AppData\Roaming")
    assert paths.data_dir() == Path(r"C:\Users\someone\AppData\Roaming") / "prompt-cache"


def test_windows_falls_back_when_appdata_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(paths.sys, "platform", "win32")
    assert paths.data_dir() == Path.home() / "AppData" / "Roaming" / "prompt-cache"


def test_linux_uses_xdg_data_home(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", "/home/someone/.local/share")
    assert paths.data_dir() == Path("/home/someone/.local/share/prompt-cache")


def test_linux_defaults_without_xdg(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(paths.sys, "platform", "linux")
    assert paths.data_dir() == Path.home() / ".local" / "share" / "prompt-cache"


def test_db_path_sits_inside_the_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv(paths.DATA_DIR_ENV, str(tmp_path))
    assert paths.db_path() == tmp_path / "prompt-cache.db"
    assert paths.db_path().parent == paths.data_dir()


def test_ensure_data_dir_creates_nested_directories(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    target = tmp_path / "a" / "b" / "c"
    monkeypatch.setenv(paths.DATA_DIR_ENV, str(target))
    assert paths.ensure_data_dir() == target
    assert target.is_dir()
    # idempotent
    assert paths.ensure_data_dir() == target
