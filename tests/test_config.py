from __future__ import annotations

import random
import subprocess
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.config import (
    TASTE_CURRENT_VERSION,
    app_data_dir,
    default_taste_text,
    ensure_taste_file,
    find_project,
    global_dir,
    load_manifest,
    load_taste,
    parse_taste_version,
    register_project,
    resolve_live_migrations_dir,
    resolve_project,
    save_manifest,
    taste_is_stale,
    xdg_data_home,
    ProjectEntry,
    ResolvedProject,
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


def test_load_manifest_rejects_non_object_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pytest as _pytest

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    manifest = tmp_path / "xdg" / "continuous-refactoring" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("[]", encoding="utf-8")

    with _pytest.raises(ContinuousRefactorError, match="malformed"):
        load_manifest()


def test_load_manifest_rejects_non_mapping_projects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pytest as _pytest

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    manifest = tmp_path / "xdg" / "continuous-refactoring" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text('{"projects": []}', encoding="utf-8")

    with _pytest.raises(ContinuousRefactorError, match="projects"):
        load_manifest()


def test_load_manifest_rejects_non_mapping_project_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pytest as _pytest

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    manifest = tmp_path / "xdg" / "continuous-refactoring" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        '{"projects": {"abc": ["not", "an", "object"]}}',
        encoding="utf-8",
    )

    with _pytest.raises(ContinuousRefactorError, match="project 'abc' must be a JSON object"):
        load_manifest()


def test_load_manifest_rejects_project_entry_missing_required_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pytest as _pytest

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    manifest = tmp_path / "xdg" / "continuous-refactoring" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        '{"projects": {"abc": {"uuid": "abc", "git_remote": null, "created_at": "x"}}}',
        encoding="utf-8",
    )

    with _pytest.raises(ContinuousRefactorError, match="missing 'path'"):
        load_manifest()


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


# ---------------------------------------------------------------------------
# live_migrations_dir
# ---------------------------------------------------------------------------

def test_entry_roundtrip_with_live_migrations_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    entry = ProjectEntry(
        uuid=str(uuid.uuid4()),
        path="/tmp/proj",
        git_remote=None,
        created_at="2025-01-01T00:00:00.000+00:00",
        live_migrations_dir=".migrations",
    )
    save_manifest({entry.uuid: entry})
    loaded = load_manifest()
    assert loaded[entry.uuid] == entry
    assert loaded[entry.uuid].live_migrations_dir == ".migrations"


def test_entry_roundtrip_without_live_migrations_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    entry = ProjectEntry(
        uuid=str(uuid.uuid4()),
        path="/tmp/proj",
        git_remote=None,
        created_at="2025-01-01T00:00:00.000+00:00",
    )
    save_manifest({entry.uuid: entry})
    loaded = load_manifest()
    assert loaded[entry.uuid] == entry
    assert loaded[entry.uuid].live_migrations_dir is None


def test_legacy_manifest_without_live_migrations_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    import json

    mpath = tmp_path / "xdg" / "continuous-refactoring" / "manifest.json"
    mpath.parent.mkdir(parents=True, exist_ok=True)
    uid = str(uuid.uuid4())
    legacy_data = {
        "projects": {
            uid: {
                "uuid": uid,
                "path": "/tmp/legacy",
                "git_remote": None,
                "created_at": "2024-01-01T00:00:00.000+00:00",
            }
        }
    }
    mpath.write_text(json.dumps(legacy_data), encoding="utf-8")

    loaded = load_manifest()
    assert uid in loaded
    assert loaded[uid].live_migrations_dir is None


def test_resolve_live_migrations_dir_none_when_unset(
    tmp_path: Path,
) -> None:
    entry = ProjectEntry(
        uuid="abc",
        path=str(tmp_path),
        git_remote=None,
        created_at="2025-01-01T00:00:00.000+00:00",
    )
    project = ResolvedProject(entry=entry, project_dir=tmp_path / "data")
    assert resolve_live_migrations_dir(project) is None


def test_resolve_live_migrations_dir_valid(
    tmp_path: Path,
) -> None:
    entry = ProjectEntry(
        uuid="abc",
        path=str(tmp_path),
        git_remote=None,
        created_at="2025-01-01T00:00:00.000+00:00",
        live_migrations_dir=".migrations",
    )
    project = ResolvedProject(entry=entry, project_dir=tmp_path / "data")
    result = resolve_live_migrations_dir(project)
    assert result == tmp_path / ".migrations"


def test_resolve_live_migrations_dir_rejects_escape(
    tmp_path: Path,
) -> None:
    entry = ProjectEntry(
        uuid="abc",
        path=str(tmp_path),
        git_remote=None,
        created_at="2025-01-01T00:00:00.000+00:00",
        live_migrations_dir="../elsewhere",
    )
    project = ResolvedProject(entry=entry, project_dir=tmp_path / "data")
    import pytest as _pytest
    with _pytest.raises(ContinuousRefactorError, match="escapes repo"):
        resolve_live_migrations_dir(project)


# ---------------------------------------------------------------------------
# Taste versioning
# ---------------------------------------------------------------------------

def test_parse_taste_version_present() -> None:
    text = "taste-scoping-version: 1\n\n- Some bullet.\n"
    assert parse_taste_version(text) == 1


def test_parse_taste_version_higher() -> None:
    text = "taste-scoping-version: 42\n\n- Bullet.\n"
    assert parse_taste_version(text) == 42


def test_parse_taste_version_missing() -> None:
    text = "- Just bullets, no header.\n- Another bullet.\n"
    assert parse_taste_version(text) is None


def test_parse_taste_version_malformed_non_integer() -> None:
    text = "taste-scoping-version: abc\n\n- Bullet.\n"
    assert parse_taste_version(text) is None


def test_parse_taste_version_malformed_empty_value() -> None:
    text = "taste-scoping-version:\n\n- Bullet.\n"
    assert parse_taste_version(text) is None


def test_parse_taste_version_empty_string() -> None:
    assert parse_taste_version("") is None


def test_taste_is_stale_legacy_no_header() -> None:
    legacy = "- Old taste without version header.\n"
    assert taste_is_stale(legacy) is True


def test_taste_is_stale_false_for_current() -> None:
    text = f"taste-scoping-version: {TASTE_CURRENT_VERSION}\n\n- Bullet.\n"
    assert taste_is_stale(text) is False


def test_taste_is_stale_true_for_wrong_version() -> None:
    text = "taste-scoping-version: 999\n\n- Bullet.\n"
    assert taste_is_stale(text) is True


def test_default_taste_has_version_header() -> None:
    text = default_taste_text()
    assert text.startswith("taste-scoping-version: 1\n")
    assert parse_taste_version(text) == TASTE_CURRENT_VERSION
    assert not taste_is_stale(text)


def test_default_taste_has_large_scope_section() -> None:
    text = default_taste_text()
    assert "## large-scope decisions" in text
    assert "split" in text.lower()
    assert "interface" in text.lower() or "abstraction" in text.lower()


def test_default_taste_has_rollout_style_section() -> None:
    text = default_taste_text()
    assert "## rollout style" in text
    assert "caution" in text.lower()
    assert "feature-flag" in text.lower()
