from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest

from conftest import init_repo, init_repo_with_temp_home

from continuous_refactoring.cli import _handle_init, _handle_taste
from continuous_refactoring.config import (
    ProjectEntry,
    default_taste_text,
    load_manifest,
    register_project,
)

def _xdg_home(tmp_path: Path) -> Path:
    return tmp_path / "xdg"


def _project_dir(xdg_path: Path, entry_uuid: str) -> Path:
    return xdg_path / "continuous-refactoring" / "projects" / entry_uuid


def _taste_path(xdg_path: Path, entry_uuid: str) -> Path:
    return _project_dir(xdg_path, entry_uuid) / "taste.md"


def _single_manifest_entry() -> ProjectEntry:
    manifest = load_manifest()
    assert len(manifest) == 1
    return next(iter(manifest.values()))


# ---------------------------------------------------------------------------
# init subcommand
# ---------------------------------------------------------------------------


def test_init_creates_manifest_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)

    args = argparse.Namespace(path=repo)
    _handle_init(args)

    entry = _single_manifest_entry()
    assert entry is not None
    assert entry.path == str(repo.resolve())


def test_init_creates_project_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)

    args = argparse.Namespace(path=repo)
    _handle_init(args)

    entry = _single_manifest_entry()
    project_dir = _project_dir(_xdg_home(tmp_path), entry.uuid)
    assert project_dir.is_dir()


def test_init_creates_taste_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)

    args = argparse.Namespace(path=repo)
    _handle_init(args)

    entry = _single_manifest_entry()
    taste = _taste_path(_xdg_home(tmp_path), entry.uuid)
    assert taste.exists()
    assert taste.read_text(encoding="utf-8") == default_taste_text()


def test_init_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    args = argparse.Namespace(path=repo)

    _handle_init(args)
    first = _single_manifest_entry()
    taste_path = _taste_path(_xdg_home(tmp_path), first.uuid)
    custom_content = "- My custom taste.\n"
    taste_path.write_text(custom_content, encoding="utf-8")

    _handle_init(args)
    second = _single_manifest_entry()
    assert first.uuid == second.uuid
    assert taste_path.read_text(encoding="utf-8") == custom_content


def test_init_with_explicit_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = init_repo_with_temp_home(
        tmp_path,
        monkeypatch,
        repo_name="explicit-project",
    )

    # cwd is NOT the repo -- explicit --path should win
    monkeypatch.chdir(tmp_path)
    args = argparse.Namespace(path=repo)
    _handle_init(args)

    entry = _single_manifest_entry()
    assert entry.path == str(repo.resolve())

    out = capsys.readouterr().out
    assert entry.uuid in out


def test_init_detects_git_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch, repo_name="with-remote")
    remote_url = "https://example.com/org/repo.git"
    subprocess.run(
        ["git", "remote", "add", "origin", remote_url],
        cwd=repo, check=True, capture_output=True,
    )

    args = argparse.Namespace(path=repo)
    _handle_init(args)

    assert _xdg_home(tmp_path).is_dir()
    entry = _single_manifest_entry()
    assert entry.git_remote == remote_url


def test_init_live_migrations_dir_creates_and_stores(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)

    args = argparse.Namespace(path=repo, live_migrations_dir=Path(".migrations"))
    _handle_init(args)

    entry = _single_manifest_entry()
    assert entry.live_migrations_dir == ".migrations"
    assert (repo / ".migrations").is_dir()

    out = capsys.readouterr().out
    assert entry.uuid in out
    assert "Live migrations dir:" in out

    # Second call is idempotent: overwrites value, no duplicate entries
    args2 = argparse.Namespace(path=repo, live_migrations_dir=Path("other-dir"))
    _handle_init(args2)

    entry2 = _single_manifest_entry()
    assert entry2.uuid == entry.uuid
    assert entry2.live_migrations_dir == "other-dir"
    assert (repo / "other-dir").is_dir()


def test_init_live_migrations_dir_rejects_outside_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)

    args = argparse.Namespace(path=repo, live_migrations_dir=Path("../outside"))
    with pytest.raises(SystemExit) as exc_info:
        _handle_init(args)

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "must be inside the repo" in err


# ---------------------------------------------------------------------------
# taste subcommand
# ---------------------------------------------------------------------------


def test_taste_prints_project_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    monkeypatch.chdir(repo)

    register_project(repo)

    args = argparse.Namespace(global_=False)
    _handle_taste(args)

    out = capsys.readouterr().out.strip()
    assert out.endswith("taste.md")
    assert Path(out).exists()


def test_taste_creates_file_if_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    monkeypatch.chdir(repo)

    project = register_project(repo)
    # Ensure it exists first, then remove it
    taste_path = project.project_dir / "taste.md"
    if taste_path.exists():
        taste_path.unlink()
    assert not taste_path.exists()

    args = argparse.Namespace(global_=False)
    _handle_taste(args)

    out = capsys.readouterr().out.strip()
    assert Path(out).exists()
    assert Path(out).read_text(encoding="utf-8") == default_taste_text()


def test_taste_global_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    init_repo_with_temp_home(tmp_path, monkeypatch, repo_name="project")

    args = argparse.Namespace(global_=True)
    _handle_taste(args)

    out = capsys.readouterr().out.strip()
    expected = _xdg_home(tmp_path) / "continuous-refactoring" / "global" / "taste.md"
    assert out == str(expected)
    assert expected.exists()
    assert expected.read_text(encoding="utf-8") == default_taste_text()


def test_taste_errors_without_init(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "unregistered"
    init_repo(repo)
    monkeypatch.chdir(repo)

    args = argparse.Namespace(global_=False)
    with pytest.raises(SystemExit) as exc_info:
        _handle_taste(args)

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "not initialized" in err
