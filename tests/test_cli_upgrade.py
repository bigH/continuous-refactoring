from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from conftest import init_repo

from continuous_refactoring.cli import _handle_upgrade
from continuous_refactoring.config import (
    CONFIG_CURRENT_VERSION,
    default_taste_text,
    global_dir,
    load_config_version,
    register_project,
)


def _upgrade_args() -> argparse.Namespace:
    return argparse.Namespace(command="upgrade")


def _set_xdg_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))


def _register_project_with_upgrade_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_xdg_home(tmp_path, monkeypatch)
    repo = tmp_path / "project"
    init_repo(repo)
    register_project(repo)


# ---------------------------------------------------------------------------
# Happy path: current config version → exit 0
# ---------------------------------------------------------------------------


def test_upgrade_succeeds_when_config_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _register_project_with_upgrade_layout(tmp_path, monkeypatch)

    _handle_upgrade(_upgrade_args())


def test_upgrade_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _register_project_with_upgrade_layout(tmp_path, monkeypatch)

    _handle_upgrade(_upgrade_args())
    _handle_upgrade(_upgrade_args())

    assert load_config_version() == CONFIG_CURRENT_VERSION


# ---------------------------------------------------------------------------
# Failure: missing config → exit 1
# ---------------------------------------------------------------------------


def test_upgrade_fails_when_config_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_xdg_home(tmp_path, monkeypatch)

    with pytest.raises(SystemExit) as exc_info:
        _handle_upgrade(_upgrade_args())

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "config version" in err


# ---------------------------------------------------------------------------
# Failure: stale config version → exit 1
# ---------------------------------------------------------------------------


def test_upgrade_fails_when_config_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_xdg_home(tmp_path, monkeypatch)

    manifest_dir = tmp_path / "xdg" / "continuous-refactoring"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "manifest.json").write_text(
        json.dumps({"projects": {}}), encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc_info:
        _handle_upgrade(_upgrade_args())

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "config version" in err


# ---------------------------------------------------------------------------
# Stale taste: warning on stderr, still exit 0
# ---------------------------------------------------------------------------


def test_upgrade_warns_on_stale_global_taste(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _register_project_with_upgrade_layout(tmp_path, monkeypatch)

    gdir = global_dir()
    gdir.mkdir(parents=True, exist_ok=True)
    (gdir / "taste.md").write_text("- Old taste without version.\n", encoding="utf-8")

    _handle_upgrade(_upgrade_args())

    err = capsys.readouterr().err
    assert "taste" in err.lower()
    assert "out of date" in err


def test_upgrade_no_taste_warning_when_current(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _register_project_with_upgrade_layout(tmp_path, monkeypatch)

    gdir = global_dir()
    gdir.mkdir(parents=True, exist_ok=True)
    (gdir / "taste.md").write_text(default_taste_text(), encoding="utf-8")

    _handle_upgrade(_upgrade_args())

    err = capsys.readouterr().err
    assert err == ""


def test_upgrade_no_taste_warning_when_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _register_project_with_upgrade_layout(tmp_path, monkeypatch)

    _handle_upgrade(_upgrade_args())

    err = capsys.readouterr().err
    assert err == ""
