from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path

__all__ = [
    "CONFIG_CURRENT_VERSION",
    "ProjectEntry",
    "ResolvedProject",
    "TASTE_CURRENT_VERSION",
    "app_data_dir",
    "config_is_current",
    "default_taste_text",
    "ensure_taste_file",
    "find_project",
    "global_dir",
    "load_config_version",
    "load_manifest",
    "load_taste",
    "manifest_path",
    "parse_taste_version",
    "register_project",
    "resolve_live_migrations_dir",
    "resolve_project",
    "save_manifest",
    "set_live_migrations_dir",
    "taste_is_stale",
    "xdg_data_home",
]

from continuous_refactoring.artifacts import ContinuousRefactorError

CONFIG_CURRENT_VERSION = 1
TASTE_CURRENT_VERSION = 1

_DEFAULT_TASTE = """\
taste-scoping-version: 1

- Validate at the edges and stay lean in the middle.
- Keep exception translation only at real boundaries and preserve causes when translating.
- Keep comments only when they explain a real boundary contract or a genuinely deferred design issue that code alone cannot make obvious.
- Remove fallback, compat, adapter, migrated, legacy, or normalize-shaped code when evidence shows it is no longer needed.
- Merge modules when splits hurt locality more than they help. Split modules when one file hides unrelated responsibilities.

## large-scope decisions
- When to split a module vs. unify related modules.
- When to introduce or remove an interface or abstraction boundary.
- When a cross-cutting concern warrants a shared library vs. inline duplication.

## rollout style
- Caution level for changes with wide blast radius.
- Feature-flag user-visible behavior changes before full rollout.
- Prefer incremental, reviewable steps over large-bang rewrites.
"""


@dataclass(frozen=True)
class ProjectEntry:
    uuid: str
    path: str
    git_remote: str | None
    created_at: str
    live_migrations_dir: str | None = None


@dataclass(frozen=True)
class ResolvedProject:
    entry: ProjectEntry
    project_dir: Path


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def xdg_data_home() -> Path:
    env = os.environ.get("XDG_DATA_HOME")
    if env:
        return Path(env)
    return Path.home() / ".local" / "share"


def app_data_dir() -> Path:
    return xdg_data_home() / "continuous-refactoring"


def global_dir() -> Path:
    return app_data_dir() / "global"


def manifest_path() -> Path:
    return app_data_dir() / "manifest.json"


# ---------------------------------------------------------------------------
# Manifest I/O
# ---------------------------------------------------------------------------

def _entry_from_dict(data: dict[str, object]) -> ProjectEntry:
    return ProjectEntry(
        uuid=str(data["uuid"]),
        path=str(data["path"]),
        git_remote=data.get("git_remote"),  # type: ignore[arg-type]
        created_at=str(data["created_at"]),
        live_migrations_dir=data.get("live_migrations_dir"),  # type: ignore[arg-type]
    )


def load_manifest() -> dict[str, ProjectEntry]:
    path = manifest_path()
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        uid: _entry_from_dict(entry)
        for uid, entry in raw.get("projects", {}).items()
    }


def save_manifest(manifest: dict[str, ProjectEntry]) -> None:
    path = manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CONFIG_CURRENT_VERSION,
        "projects": {uid: asdict(entry) for uid, entry in manifest.items()},
    }
    content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, str(path))
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def load_config_version() -> int | None:
    path = manifest_path()
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    version = raw.get("version")
    return version if isinstance(version, int) else None


def config_is_current() -> bool:
    return load_config_version() == CONFIG_CURRENT_VERSION


# ---------------------------------------------------------------------------
# Project lookup / registration
# ---------------------------------------------------------------------------

def find_project(
    path: Path, manifest: dict[str, ProjectEntry]
) -> ProjectEntry | None:
    resolved = str(path.resolve())
    for entry in manifest.values():
        if entry.path == resolved:
            return entry
    return None


def _detect_git_remote(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _project_dir(uid: str) -> Path:
    return app_data_dir() / "projects" / uid


def register_project(path: Path) -> ResolvedProject:
    resolved = path.resolve()
    manifest = load_manifest()
    existing = find_project(resolved, manifest)
    if existing is not None:
        return ResolvedProject(
            entry=existing,
            project_dir=_project_dir(existing.uuid),
        )

    uid = str(uuid.uuid4())
    entry = ProjectEntry(
        uuid=uid,
        path=str(resolved),
        git_remote=_detect_git_remote(resolved),
        created_at=datetime.now().astimezone().isoformat(timespec="milliseconds"),
    )
    manifest[uid] = entry
    save_manifest(manifest)
    project_dir = _project_dir(uid)
    project_dir.mkdir(parents=True, exist_ok=True)
    return ResolvedProject(entry=entry, project_dir=project_dir)


def resolve_project(path: Path) -> ResolvedProject:
    manifest = load_manifest()
    entry = find_project(path, manifest)
    if entry is None:
        raise ContinuousRefactorError(
            f"Project not registered: {path.resolve()}"
        )
    return ResolvedProject(entry=entry, project_dir=_project_dir(entry.uuid))


def resolve_live_migrations_dir(project: ResolvedProject) -> Path | None:
    if project.entry.live_migrations_dir is None:
        return None
    repo_root = Path(project.entry.path)
    resolved = (repo_root / project.entry.live_migrations_dir).resolve()
    if not resolved.is_relative_to(repo_root):
        raise ContinuousRefactorError(
            f"live_migrations_dir escapes repo: {project.entry.live_migrations_dir}"
        )
    return resolved


def set_live_migrations_dir(project_uuid: str, relative_dir: str) -> None:
    manifest = load_manifest()
    old = manifest[project_uuid]
    manifest[project_uuid] = replace(old, live_migrations_dir=relative_dir)
    save_manifest(manifest)


# ---------------------------------------------------------------------------
# Taste
# ---------------------------------------------------------------------------

def parse_taste_version(text: str) -> int | None:
    first_line = text.split("\n", 1)[0].strip()
    prefix = "taste-scoping-version:"
    if not first_line.startswith(prefix):
        return None
    raw = first_line[len(prefix):].strip()
    try:
        return int(raw)
    except ValueError:
        return None


def taste_is_stale(text: str) -> bool:
    return parse_taste_version(text) != TASTE_CURRENT_VERSION


def default_taste_text() -> str:
    return _DEFAULT_TASTE


def ensure_taste_file(path: Path) -> Path:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_DEFAULT_TASTE, encoding="utf-8")
    return path


def load_taste(project: ResolvedProject | None) -> str:
    if project is not None:
        project_taste = project.project_dir / "taste.md"
        if project_taste.exists():
            return project_taste.read_text(encoding="utf-8")

    global_taste = global_dir() / "taste.md"
    if global_taste.exists():
        return global_taste.read_text(encoding="utf-8")

    return _DEFAULT_TASTE
