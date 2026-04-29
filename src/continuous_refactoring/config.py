from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from collections.abc import Mapping

from continuous_refactoring.artifacts import ContinuousRefactorError

__all__ = [
    "CONFIG_CURRENT_VERSION",
    "DEFAULT_REPO_TASTE_PATH",
    "ProjectEntry",
    "ResolvedProject",
    "TASTE_CURRENT_VERSION",
    "app_data_dir",
    "config_is_current",
    "default_taste_text",
    "ensure_taste_file",
    "failure_snapshots_dir",
    "find_project",
    "global_dir",
    "load_config_version",
    "load_manifest",
    "load_taste",
    "manifest_path",
    "parse_taste_version",
    "register_project",
    "resolve_live_migrations_dir",
    "resolve_project_taste_path",
    "resolve_project",
    "save_manifest",
    "set_live_migrations_dir",
    "set_repo_taste_path",
    "taste_is_stale",
    "xdg_data_home",
]

CONFIG_CURRENT_VERSION = 1
TASTE_CURRENT_VERSION = 1
DEFAULT_REPO_TASTE_PATH = ".continuous-refactoring/taste.md"

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
    repo_taste_path: str | None = None


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

def _load_manifest_payload() -> dict[str, object]:
    path = manifest_path()
    if not path.exists():
        return {}
    raw_text = _read_manifest_text()
    return _parse_manifest_payload(raw_text)


def _read_manifest_text() -> str:
    try:
        return manifest_path().read_text(encoding="utf-8")
    except OSError as exc:
        raise ContinuousRefactorError(
            "Manifest file could not be read."
        ) from exc


def _parse_manifest_payload(text: str) -> dict[str, object]:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContinuousRefactorError(
            "Manifest file is malformed: invalid JSON."
        ) from exc
    if not isinstance(raw, dict):
        raise ContinuousRefactorError(
            "Manifest file is malformed: expected a JSON object."
        )
    return raw


def _string_field(
    data: Mapping[str, object],
    key: str,
    *,
    project_id: str,
    required: bool,
) -> str | None:
    value = data.get(key)
    if value is None:
        if required:
            raise ContinuousRefactorError(
                f"Manifest file is malformed: project '{project_id}' missing '{key}'."
            )
        return None
    if not isinstance(value, str):
        raise ContinuousRefactorError(
            f"Manifest file is malformed: project '{project_id}' field '{key}' must be a string."
        )
    return value


def _entry_from_object(uid: str, data: object) -> ProjectEntry:
    if not isinstance(data, dict):
        raise ContinuousRefactorError(
            f"Manifest file is malformed: project '{uid}' must be a JSON object."
        )
    entry_uuid = _string_field(data, "uuid", project_id=uid, required=True)
    if entry_uuid != uid:
        raise ContinuousRefactorError(
            f"Manifest file is malformed: project '{uid}' uuid mismatch."
        )
    return ProjectEntry(
        uuid=entry_uuid,
        path=_string_field(data, "path", project_id=uid, required=True),
        git_remote=_string_field(
            data,
            "git_remote",
            project_id=uid,
            required=False,
        ),
        created_at=_string_field(data, "created_at", project_id=uid, required=True),
        live_migrations_dir=_string_field(
            data,
            "live_migrations_dir",
            project_id=uid,
            required=False,
        ),
        repo_taste_path=_string_field(
            data,
            "repo_taste_path",
            project_id=uid,
            required=False,
        ),
    )


def load_manifest() -> dict[str, ProjectEntry]:
    payload = _load_manifest_payload()
    projects_raw = payload.get("projects", {})
    if not isinstance(projects_raw, dict):
        raise ContinuousRefactorError(
            "Manifest file is malformed: 'projects' must be a JSON object."
        )
    return {uid: _entry_from_object(uid, entry) for uid, entry in projects_raw.items()}


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
    payload = _load_manifest_payload()
    version = payload.get("version")
    return version if isinstance(version, int) else None


def config_is_current() -> bool:
    return load_config_version() == CONFIG_CURRENT_VERSION


# ---------------------------------------------------------------------------
# Project lookup / registration
# ---------------------------------------------------------------------------

def find_project(
    path: Path, manifest: dict[str, ProjectEntry]
) -> ProjectEntry | None:
    for entry in manifest.values():
        if _project_path_matches(path, entry.path):
            return entry
    return None


def _project_path_matches(path: Path, stored_path: str) -> bool:
    return path.resolve() == Path(stored_path).resolve()


def _detect_git_remote(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=path,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _resolved(entry: ProjectEntry) -> ResolvedProject:
    project_dir = app_data_dir() / "projects" / entry.uuid
    project_dir.mkdir(parents=True, exist_ok=True)
    return ResolvedProject(entry=entry, project_dir=project_dir)


def failure_snapshots_dir(path: Path) -> Path:
    snapshot_dir = register_project(path).project_dir / "failures"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    return snapshot_dir


def register_project(path: Path) -> ResolvedProject:
    resolved = path.resolve()
    manifest = load_manifest()
    existing = find_project(resolved, manifest)
    if existing is not None:
        return _resolved(existing)

    uid = str(uuid.uuid4())
    entry = ProjectEntry(
        uuid=uid,
        path=str(resolved),
        git_remote=_detect_git_remote(resolved),
        created_at=datetime.now().astimezone().isoformat(timespec="milliseconds"),
    )
    manifest[uid] = entry
    save_manifest(manifest)
    return _resolved(entry)


def resolve_project(path: Path) -> ResolvedProject:
    manifest = load_manifest()
    entry = find_project(path, manifest)
    if entry is None:
        raise ContinuousRefactorError(
            f"Project not registered: {path.resolve()}"
        )
    return _resolved(entry)


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


def resolve_project_taste_path(project: ResolvedProject) -> Path:
    if project.entry.repo_taste_path is None:
        return project.project_dir / "taste.md"
    repo_root = Path(project.entry.path).resolve()
    resolved = (repo_root / project.entry.repo_taste_path).resolve()
    if not resolved.is_relative_to(repo_root):
        raise ContinuousRefactorError(
            f"repo_taste_path escapes repo: {project.entry.repo_taste_path}"
        )
    return resolved


def _get_project(manifest: dict[str, ProjectEntry], project_uuid: str) -> ProjectEntry:
    project = manifest.get(project_uuid)
    if project is None:
        raise ContinuousRefactorError(f"Project not registered: {project_uuid}")
    return project


def set_live_migrations_dir(project_uuid: str, relative_dir: str) -> None:
    manifest = load_manifest()
    old = _get_project(manifest, project_uuid)
    manifest[project_uuid] = replace(old, live_migrations_dir=relative_dir)
    save_manifest(manifest)


def set_repo_taste_path(project_uuid: str, relative_path: str) -> None:
    manifest = load_manifest()
    old = _get_project(manifest, project_uuid)
    manifest[project_uuid] = replace(old, repo_taste_path=relative_path)
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
    if path.exists() and not path.is_file():
        raise ContinuousRefactorError(f"Taste path is not a file: {path}")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_DEFAULT_TASTE, encoding="utf-8")
    return path


def _read_taste_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContinuousRefactorError(
            f"Taste file could not be read: {path}"
        ) from exc


def load_taste(project: ResolvedProject | None) -> str:
    if project is not None:
        project_taste = resolve_project_taste_path(project)
        if project_taste.exists():
            return _read_taste_text(project_taste)

    global_taste = global_dir() / "taste.md"
    if global_taste.exists():
        return _read_taste_text(global_taste)

    return _DEFAULT_TASTE
