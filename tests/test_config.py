from __future__ import annotations

import random
import subprocess
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from continuous_refactoring.config import (
    app_data_dir,
    default_taste_text,
    ensure_taste_file,
    find_project,
    global_dir,
    load_manifest,
    load_taste,
    register_project,
    resolve_project,
    save_manifest,
    taste_file_path,
    xdg_data_home,
    ProjectEntry,
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
# XDG helpers
# ---------------------------------------------------------------------------

def test_xdg_data_home_uses_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom = tmp_path / "custom-xdg"
    monkeypatch.setenv("XDG_DATA_HOME", str(custom))
    assert xdg_data_home() == custom


def test_xdg_data_home_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    result = xdg_data_home()
    assert result == Path.home() / ".local" / "share"


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def test_load_manifest_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert load_manifest() == {}


def test_save_and_load_manifest_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    entry_a = ProjectEntry(
        uuid=str(uuid.uuid4()),
        path="/tmp/project-a",
        git_remote="https://github.com/a/a.git",
        created_at="2025-01-01T00:00:00.000+00:00",
    )
    entry_b = ProjectEntry(
        uuid=str(uuid.uuid4()),
        path="/tmp/project-b",
        git_remote=None,
        created_at="2025-06-15T12:00:00.000+00:00",
    )
    manifest = {entry_a.uuid: entry_a, entry_b.uuid: entry_b}

    save_manifest(manifest)
    loaded = load_manifest()

    assert loaded == manifest


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_register_project_creates_uuid_and_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    project_path = tmp_path / "my-project"
    _init_repo(project_path)

    resolved = register_project(project_path)

    # Valid UUIDv4
    parsed = uuid.UUID(resolved.entry.uuid, version=4)
    assert str(parsed) == resolved.entry.uuid

    # Project dir exists
    assert resolved.project_dir.is_dir()

    # Manifest updated
    manifest = load_manifest()
    assert resolved.entry.uuid in manifest


def test_register_project_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    project_path = tmp_path / "my-project"
    _init_repo(project_path)

    first = register_project(project_path)
    second = register_project(project_path)

    assert first.entry.uuid == second.entry.uuid

    manifest = load_manifest()
    assert len(manifest) == 1


def test_register_project_detects_git_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    project_path = tmp_path / "with-remote"
    _init_repo(project_path)
    remote_url = "https://example.com/test/repo.git"
    subprocess.run(
        ["git", "remote", "add", "origin", remote_url],
        cwd=project_path, check=True, capture_output=True,
    )

    resolved = register_project(project_path)
    assert resolved.entry.git_remote == remote_url


def test_register_project_no_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    project_path = tmp_path / "no-remote"
    _init_repo(project_path)

    resolved = register_project(project_path)
    assert resolved.entry.git_remote is None


def test_find_project_resolves_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    project_path = tmp_path / "findme"
    _init_repo(project_path)

    registered = register_project(project_path)
    manifest = load_manifest()

    # Look up using the same path (resolved internally)
    found = find_project(project_path, manifest)
    assert found is not None
    assert found.uuid == registered.entry.uuid


# ---------------------------------------------------------------------------
# Taste
# ---------------------------------------------------------------------------

def test_load_taste_project_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    project_path = tmp_path / "taste-proj"
    _init_repo(project_path)

    resolved = register_project(project_path)
    taste_content = "- My custom taste rule.\n"
    (resolved.project_dir / "taste.md").write_text(taste_content, encoding="utf-8")

    assert load_taste(resolved) == taste_content


def test_load_taste_global_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    project_path = tmp_path / "taste-global"
    _init_repo(project_path)

    resolved = register_project(project_path)

    global_taste = "- Global taste rule.\n"
    gdir = global_dir()
    gdir.mkdir(parents=True, exist_ok=True)
    (gdir / "taste.md").write_text(global_taste, encoding="utf-8")

    assert load_taste(resolved) == global_taste


def test_load_taste_builtin_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    project_path = tmp_path / "taste-default"
    _init_repo(project_path)

    resolved = register_project(project_path)
    assert load_taste(resolved) == default_taste_text()


def test_load_taste_project_overrides_global(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    project_path = tmp_path / "taste-override"
    _init_repo(project_path)

    resolved = register_project(project_path)

    project_taste = "- Project-level wins.\n"
    (resolved.project_dir / "taste.md").write_text(project_taste, encoding="utf-8")

    global_taste = "- Global-level loses.\n"
    gdir = global_dir()
    gdir.mkdir(parents=True, exist_ok=True)
    (gdir / "taste.md").write_text(global_taste, encoding="utf-8")

    assert load_taste(resolved) == project_taste


def test_ensure_taste_file_creates_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    target = tmp_path / "xdg" / "continuous-refactoring" / "global" / "taste.md"

    result = ensure_taste_file(target)

    assert result == target
    assert target.exists()
    assert target.read_text(encoding="utf-8") == default_taste_text()


def test_ensure_taste_file_preserves_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    target = tmp_path / "xdg" / "continuous-refactoring" / "global" / "taste.md"
    target.parent.mkdir(parents=True, exist_ok=True)

    custom = "- Do not touch me.\n"
    target.write_text(custom, encoding="utf-8")

    ensure_taste_file(target)
    assert target.read_text(encoding="utf-8") == custom


# ---------------------------------------------------------------------------
# Property-based: manifest roundtrip
# ---------------------------------------------------------------------------

def test_manifest_roundtrip_property(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    rng = random.Random(42)
    entries: dict[str, ProjectEntry] = {}
    for _ in range(rng.randint(5, 20)):
        uid = str(uuid.uuid4())
        depth = rng.randint(1, 4)
        segments = [
            "".join(rng.choices("abcdefghijklmnop", k=rng.randint(3, 8)))
            for _ in range(depth)
        ]
        path = "/" + "/".join(segments)
        has_remote = rng.choice([True, False])
        remote = f"https://github.com/{segments[0]}/{segments[-1]}.git" if has_remote else None
        entry = ProjectEntry(
            uuid=uid,
            path=path,
            git_remote=remote,
            created_at=f"2025-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}T00:00:00.000+00:00",
        )
        entries[uid] = entry

    save_manifest(entries)
    loaded = load_manifest()
    assert loaded == entries
