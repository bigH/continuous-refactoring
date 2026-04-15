from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest

from continuous_refactoring.cli import _handle_review_list, _handle_review_perform
from continuous_refactoring.config import register_project, set_live_migrations_dir
from continuous_refactoring.migrations import (
    MigrationManifest,
    load_manifest as load_migration_manifest,
    save_manifest as save_migration,
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


def _make_manifest(
    name: str,
    *,
    awaiting_human_review: bool = False,
    status: str = "ready",
    current_phase: int = 0,
    last_touch: str = "2025-01-01T00:00:00+00:00",
) -> MigrationManifest:
    return MigrationManifest(
        name=name,
        created_at="2025-01-01T00:00:00+00:00",
        last_touch=last_touch,
        wake_up_on=None,
        awaiting_human_review=awaiting_human_review,
        status=status,
        current_phase=current_phase,
        phases=(),
    )


def test_review_list_filters_flagged_migrations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)
    monkeypatch.chdir(repo)

    project = register_project(repo)
    live_dir = repo / ".migrations"
    live_dir.mkdir()
    set_live_migrations_dir(project.entry.uuid, ".migrations")

    save_migration(
        _make_manifest(
            "mig-a",
            awaiting_human_review=True,
            status="ready",
            current_phase=1,
            last_touch="2025-03-01T12:00:00+00:00",
        ),
        live_dir / "mig-a" / "manifest.json",
    )
    save_migration(
        _make_manifest(
            "mig-b",
            awaiting_human_review=True,
            status="in-progress",
            current_phase=2,
            last_touch="2025-03-02T14:00:00+00:00",
        ),
        live_dir / "mig-b" / "manifest.json",
    )
    save_migration(
        _make_manifest("mig-c", awaiting_human_review=False, status="done"),
        live_dir / "mig-c" / "manifest.json",
    )

    _handle_review_list()

    out = capsys.readouterr().out
    lines = [line for line in out.strip().splitlines() if line]
    assert len(lines) == 2

    fields_a = lines[0].split("\t")
    assert fields_a == ["mig-a", "ready", "1", "2025-03-01T12:00:00+00:00"]

    fields_b = lines[1].split("\t")
    assert fields_b == ["mig-b", "in-progress", "2", "2025-03-02T14:00:00+00:00"]


def test_review_list_exits_1_when_no_live_migrations_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)
    monkeypatch.chdir(repo)

    register_project(repo)

    with pytest.raises(SystemExit) as exc_info:
        _handle_review_list()

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "live-migrations-dir" in err


def test_review_perform_exits_2_when_project_not_initialized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)
    monkeypatch.chdir(repo)

    with pytest.raises(SystemExit) as exc_info:
        _handle_review_perform(_make_perform_args("my-mig"))

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "project not initialized" in err


def _make_perform_args(migration: str) -> argparse.Namespace:
    return argparse.Namespace(
        migration=migration,
        agent="codex",
        model="test-model",
        effort="low",
    )


def _setup_review_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    awaiting: bool = True,
) -> tuple[Path, Path]:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)
    monkeypatch.chdir(repo)

    project = register_project(repo)
    live_dir = repo / ".migrations"
    live_dir.mkdir()
    set_live_migrations_dir(project.entry.uuid, ".migrations")

    save_migration(
        _make_manifest("my-mig", awaiting_human_review=awaiting, status="ready"),
        live_dir / "my-mig" / "manifest.json",
    )
    return repo, live_dir


def test_review_perform_happy_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, live_dir = _setup_review_project(tmp_path, monkeypatch, awaiting=True)
    manifest_path = live_dir / "my-mig" / "manifest.json"

    def fake_interactive(
        agent: str, model: str, effort: str, prompt: str, repo_root: Path,
    ) -> int:
        manifest = load_migration_manifest(manifest_path)
        from dataclasses import replace
        updated = replace(manifest, awaiting_human_review=False)
        save_migration(updated, manifest_path)
        return 0

    monkeypatch.setattr(
        "continuous_refactoring.cli.run_agent_interactive", fake_interactive,
    )

    _handle_review_perform(_make_perform_args("my-mig"))


def test_review_perform_exits_1_when_flag_not_cleared(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, live_dir = _setup_review_project(tmp_path, monkeypatch, awaiting=True)

    def fake_interactive(
        agent: str, model: str, effort: str, prompt: str, repo_root: Path,
    ) -> int:
        return 0

    monkeypatch.setattr(
        "continuous_refactoring.cli.run_agent_interactive", fake_interactive,
    )

    with pytest.raises(SystemExit) as exc_info:
        _handle_review_perform(_make_perform_args("my-mig"))

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "not completed" in err


def test_review_perform_exits_2_when_migration_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)
    monkeypatch.chdir(repo)

    project = register_project(repo)
    live_dir = repo / ".migrations"
    live_dir.mkdir()
    set_live_migrations_dir(project.entry.uuid, ".migrations")

    with pytest.raises(SystemExit) as exc_info:
        _handle_review_perform(_make_perform_args("nonexistent"))

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "does not exist" in err


def test_review_perform_exits_2_when_not_flagged_for_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, live_dir = _setup_review_project(tmp_path, monkeypatch, awaiting=False)

    with pytest.raises(SystemExit) as exc_info:
        _handle_review_perform(_make_perform_args("my-mig"))

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "not flagged" in err
