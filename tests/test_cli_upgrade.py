from __future__ import annotations

import argparse
import json
from collections.abc import Callable
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

_LEGACY_TASTE = "- Old taste without version.\n"


def _upgrade_args() -> argparse.Namespace:
    return argparse.Namespace(command="upgrade")


def _set_xdg_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    xdg_root = tmp_path / "xdg"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))
    return xdg_root


def _register_project_with_upgrade_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_xdg_home(tmp_path, monkeypatch)
    repo = tmp_path / "project"
    init_repo(repo)
    register_project(repo)


def _write_stale_config_manifest(xdg_root: Path) -> None:
    manifest_dir = xdg_root / "continuous-refactoring"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "manifest.json").write_text(
        json.dumps({"projects": {}}), encoding="utf-8",
    )


def _write_global_taste(text: str) -> None:
    gdir = global_dir()
    gdir.mkdir(parents=True, exist_ok=True)
    (gdir / "taste.md").write_text(text, encoding="utf-8")


def _assert_upgrade_fails_for_bad_config(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        _handle_upgrade(_upgrade_args())

    assert exc_info.value.code == 1
    assert "config version" in capsys.readouterr().err


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
# Failure: missing or stale config → exit 1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prepare_config",
    [
        lambda xdg_root: None,
        _write_stale_config_manifest,
    ],
    ids=["missing", "stale"],
)
def test_upgrade_fails_for_missing_or_stale_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    prepare_config: Callable[[Path], None],
) -> None:
    xdg_root = _set_xdg_home(tmp_path, monkeypatch)
    prepare_config(xdg_root)
    _assert_upgrade_fails_for_bad_config(capsys)


# ---------------------------------------------------------------------------
# Stale taste: warning on stderr, still exit 0
# ---------------------------------------------------------------------------


def test_upgrade_warns_on_stale_global_taste(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _register_project_with_upgrade_layout(tmp_path, monkeypatch)
    _write_global_taste(_LEGACY_TASTE)

    _handle_upgrade(_upgrade_args())

    err = capsys.readouterr().err
    assert "taste" in err.lower()
    assert "out of date" in err


@pytest.mark.parametrize(
    "taste_text",
    [default_taste_text(), None],
    ids=["current", "absent"],
)
def test_upgrade_skips_taste_warning_when_global_taste_is_current_or_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    taste_text: str | None,
) -> None:
    _register_project_with_upgrade_layout(tmp_path, monkeypatch)
    if taste_text is not None:
        _write_global_taste(taste_text)

    _handle_upgrade(_upgrade_args())

    assert capsys.readouterr().err == ""
