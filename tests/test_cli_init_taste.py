from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from continuous_refactoring.cli import _handle_init, _handle_taste
from continuous_refactoring.config import (
    default_taste_text,
    load_manifest,
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


# ---------------------------------------------------------------------------
# init subcommand
# ---------------------------------------------------------------------------


def test_init_creates_manifest_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)

    args = argparse.Namespace(path=repo)
    _handle_init(args)

    manifest = load_manifest()
    assert len(manifest) == 1
    entry = next(iter(manifest.values()))
    assert entry.path == str(repo.resolve())


def test_init_creates_project_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)

    args = argparse.Namespace(path=repo)
    _handle_init(args)

    manifest = load_manifest()
    entry = next(iter(manifest.values()))
    project_dir = (
        tmp_path / "xdg" / "continuous-refactoring" / "projects" / entry.uuid
    )
    assert project_dir.is_dir()


def test_init_creates_taste_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)

    args = argparse.Namespace(path=repo)
    _handle_init(args)

    manifest = load_manifest()
    entry = next(iter(manifest.values()))
    taste = (
        tmp_path / "xdg" / "continuous-refactoring" / "projects" / entry.uuid / "taste.md"
    )
    assert taste.exists()
    assert taste.read_text(encoding="utf-8") == default_taste_text()


def test_init_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)

    first = register_project(repo)
    taste_path = first.project_dir / "taste.md"
    taste_path.parent.mkdir(parents=True, exist_ok=True)
    custom_content = "- My custom taste.\n"
    taste_path.write_text(custom_content, encoding="utf-8")

    second = register_project(repo)
    assert first.entry.uuid == second.entry.uuid
    assert taste_path.read_text(encoding="utf-8") == custom_content


def test_init_with_explicit_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "explicit-project"
    _init_repo(repo)

    # cwd is NOT the repo -- explicit --path should win
    monkeypatch.chdir(tmp_path)
    args = argparse.Namespace(path=repo)
    _handle_init(args)

    manifest = load_manifest()
    entry = next(iter(manifest.values()))
    assert entry.path == str(repo.resolve())

    out = capsys.readouterr().out
    assert entry.uuid in out


def test_init_detects_git_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "with-remote"
    _init_repo(repo)
    remote_url = "https://example.com/org/repo.git"
    subprocess.run(
        ["git", "remote", "add", "origin", remote_url],
        cwd=repo, check=True, capture_output=True,
    )

    args = argparse.Namespace(path=repo)
    _handle_init(args)

    manifest = load_manifest()
    entry = next(iter(manifest.values()))
    assert entry.git_remote == remote_url


# ---------------------------------------------------------------------------
# taste subcommand
# ---------------------------------------------------------------------------


def test_taste_prints_project_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)
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
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)
    monkeypatch.chdir(repo)

    project = register_project(repo)
    taste_path = project.project_dir / "taste.md"
    # Ensure it exists first, then remove it
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
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    args = argparse.Namespace(global_=True)
    _handle_taste(args)

    out = capsys.readouterr().out.strip()
    expected = tmp_path / "xdg" / "continuous-refactoring" / "global" / "taste.md"
    assert out == str(expected)
    assert expected.exists()
    assert expected.read_text(encoding="utf-8") == default_taste_text()


def test_taste_errors_without_init(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import pytest

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "unregistered"
    _init_repo(repo)
    monkeypatch.chdir(repo)

    args = argparse.Namespace(global_=False)
    with pytest.raises(SystemExit) as exc_info:
        _handle_taste(args)

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "not initialized" in err
