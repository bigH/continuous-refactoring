from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, cast, get_args

from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.effort import EffortTier

__all__ = [
    "advance_phase_cursor",
    "complete_manifest_phase",
    "MigrationManifest",
    "PhaseSpec",
    "MIGRATION_STATUSES",
    "phase_file_reference",
    "has_executable_phase",
    "approaches_dir",
    "bump_last_touch",
    "eligible_now",
    "intentional_skips_dir",
    "load_manifest",
    "migration_root",
    "resolve_current_phase",
    "save_manifest",
]

MigrationStatus = Literal["planning", "ready", "in-progress", "skipped", "done"]
MIGRATION_STATUSES = cast(
    tuple[MigrationStatus, ...], get_args(MigrationStatus)
)


@dataclass(frozen=True)
class PhaseSpec:
    name: str
    file: str
    done: bool
    precondition: str
    required_effort: EffortTier | None = None
    effort_reason: str | None = None


@dataclass(frozen=True)
class MigrationManifest:
    name: str
    created_at: str
    last_touch: str
    wake_up_on: str | None
    awaiting_human_review: bool
    status: MigrationStatus
    current_phase: str
    phases: tuple[PhaseSpec, ...]
    human_review_reason: str | None = None
    cooldown_until: str | None = None


from continuous_refactoring.migration_manifest_codec import (  # noqa: E402
    decode_manifest_payload,
    encode_manifest_payload,
)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def migration_root(live_dir: Path, name: str) -> Path:
    return live_dir / name


def approaches_dir(live_dir: Path, name: str) -> Path:
    return migration_root(live_dir, name) / "approaches"


def intentional_skips_dir(live_dir: Path) -> Path:
    return live_dir / "__intentional_skips__"


def phase_file_reference(phase: PhaseSpec) -> str:
    return Path(phase.file).as_posix()


def _phase_entry(
    phases: tuple[PhaseSpec, ...], phase_name: str,
) -> tuple[int, PhaseSpec] | None:
    for index, phase in enumerate(phases):
        if phase.name == phase_name:
            return index, phase
    return None


def _require_phase_entry(
    phases: tuple[PhaseSpec, ...], phase_name: str, *, error_message: str,
) -> tuple[int, PhaseSpec]:
    phase_entry = _phase_entry(phases, phase_name)
    if phase_entry is None:
        raise ContinuousRefactorError(error_message)
    return phase_entry


def has_executable_phase(manifest: MigrationManifest) -> bool:
    """Whether the manifest's current_phase addresses an existing phase."""
    return _phase_entry(manifest.phases, manifest.current_phase) is not None


def resolve_current_phase(manifest: MigrationManifest) -> PhaseSpec:
    _, phase = _require_phase_entry(
        manifest.phases,
        manifest.current_phase,
        error_message=(
            f"Current phase {manifest.current_phase!r} "
            "does not match any phase name"
        ),
    )
    return phase


def advance_phase_cursor(
    manifest: MigrationManifest, completed_phase_name: str,
) -> str | None:
    phase_index, _ = _require_phase_entry(
        manifest.phases,
        completed_phase_name,
        error_message=f"Cannot advance unknown phase {completed_phase_name!r}",
    )
    next_index = phase_index + 1
    if next_index >= len(manifest.phases):
        return None
    return manifest.phases[next_index].name


def complete_manifest_phase(
    manifest: MigrationManifest,
    completed_phase_name: str,
    completed_at: str,
) -> MigrationManifest:
    phase_index, _ = _require_phase_entry(
        manifest.phases,
        completed_phase_name,
        error_message=f"Cannot complete unknown phase {completed_phase_name!r}",
    )
    updated_phases = tuple(
        replace(manifest_phase, done=True) if index == phase_index else manifest_phase
        for index, manifest_phase in enumerate(manifest.phases)
    )
    updated_manifest = replace(
        manifest,
        phases=updated_phases,
        last_touch=completed_at,
        wake_up_on=None,
        awaiting_human_review=False,
        human_review_reason=None,
        cooldown_until=None,
    )
    next_index = phase_index + 1
    next_phase_name = (
        manifest.phases[next_index].name
        if next_index < len(manifest.phases)
        else None
    )
    if next_phase_name is None:
        return replace(updated_manifest, current_phase="", status="done")
    return replace(updated_manifest, current_phase=next_phase_name)


# ---------------------------------------------------------------------------
# Manifest I/O
# ---------------------------------------------------------------------------


def load_manifest(path: Path) -> MigrationManifest:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ContinuousRefactorError(
            f"Could not load manifest {path}: {error}"
        ) from error
    try:
        raw = json.loads(content)
    except json.JSONDecodeError as error:
        raise ContinuousRefactorError(
            f"Could not parse manifest {path}: {error}"
        ) from error
    return decode_manifest_payload(raw)


def save_manifest(manifest: MigrationManifest, path: Path) -> None:
    content = encode_manifest_payload(manifest)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ContinuousRefactorError(
            f"Could not save manifest {path}: {error}"
        ) from error

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
        ) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(content)
    except OSError as error:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        raise ContinuousRefactorError(
            f"Could not save manifest {path}: {error}"
        ) from error

    try:
        tmp_path.replace(path)
    except OSError as error:
        tmp_path.unlink(missing_ok=True)
        raise ContinuousRefactorError(
            f"Could not save manifest {path}: {error}"
        ) from error


# ---------------------------------------------------------------------------
# Wake-up eligibility
# ---------------------------------------------------------------------------

_COOLDOWN = timedelta(hours=6)
_STALE = timedelta(days=7)


def eligible_now(manifest: MigrationManifest, now: datetime) -> bool:
    if manifest.cooldown_until is not None:
        if datetime.fromisoformat(manifest.cooldown_until) > now:
            return False
    if manifest.wake_up_on is None:
        return True
    elapsed = now - datetime.fromisoformat(manifest.last_touch)
    return datetime.fromisoformat(manifest.wake_up_on) <= now or elapsed >= _STALE


def bump_last_touch(manifest: MigrationManifest, now: datetime) -> MigrationManifest:
    return replace(manifest, last_touch=now.isoformat(timespec="milliseconds"))
