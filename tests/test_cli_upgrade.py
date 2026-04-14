from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from continuous_refactoring.cli import _handle_upgrade
from continuous_refactoring.config import (
    default_taste_text,
    global_dir,
    load_config_version,
    register_project,
)


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=path, check=True, capture_output=True,
    )
    (path / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "README.md"], cwd=path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True,
    )


def _upgrade_args() -> argparse.Namespace:
    return argparse.Namespace(command="upgrade")


# ---------------------------------------------------------------------------
# Happy path: current config version → exit 0
# ---------------------------------------------------------------------------


def test_upgrade_succeeds_when_config_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)
    register_project(repo)

    _handle_upgrade(_upgrade_args())


def test_upgrade_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)
    register_project(repo)

    _handle_upgrade(_upgrade_args())
    _handle_upgrade(_upgrade_args())

    assert load_config_version() == 1


# ---------------------------------------------------------------------------
# Failure: missing config → exit 1
# ---------------------------------------------------------------------------


def test_upgrade_fails_when_config_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import pytest as _pytest

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    with _pytest.raises(SystemExit) as exc_info:
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
    import pytest as _pytest

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    manifest_dir = tmp_path / "xdg" / "continuous-refactoring"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "manifest.json").write_text(
        json.dumps({"projects": {}}), encoding="utf-8",
    )

    with _pytest.raises(SystemExit) as exc_info:
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
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)
    register_project(repo)

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
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)
    register_project(repo)

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
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)
    register_project(repo)

    _handle_upgrade(_upgrade_args())

    err = capsys.readouterr().err
    assert err == ""
