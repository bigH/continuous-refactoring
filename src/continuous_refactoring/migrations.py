from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, cast, get_args

from continuous_refactoring.artifacts import ContinuousRefactorError

__all__ = [
    "advance_phase_cursor",
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
_VALID_STATUSES: frozenset[str] = frozenset(
    cast(tuple[str, ...], MIGRATION_STATUSES)
)


@dataclass(frozen=True)
class PhaseSpec:
    name: str
    file: str
    done: bool
    precondition: str


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


def _phase_index(phases: tuple[PhaseSpec, ...], phase_name: str) -> int | None:
    for index, phase in enumerate(phases):
        if phase.name == phase_name:
            return index
    return None


def _require_unique_phase_names(phases: tuple[PhaseSpec, ...]) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for phase in phases:
        if phase.name in seen:
            duplicates.append(phase.name)
            continue
        seen.add(phase.name)
    if duplicates:
        repeated = ", ".join(sorted(set(duplicates)))
        raise ContinuousRefactorError(
            f"Duplicate phase names are not allowed: {repeated}"
        )


def has_executable_phase(manifest: MigrationManifest) -> bool:
    """Whether the manifest's current_phase addresses an existing phase."""
    return _phase_index(manifest.phases, manifest.current_phase) is not None


def resolve_current_phase(manifest: MigrationManifest) -> PhaseSpec:
    phase_index = _phase_index(manifest.phases, manifest.current_phase)
    if phase_index is None:
        raise ContinuousRefactorError(
            f"Current phase {manifest.current_phase!r} does not match any phase name"
        )
    return manifest.phases[phase_index]


def advance_phase_cursor(
    manifest: MigrationManifest, completed_phase_name: str,
) -> str | None:
    phase_index = _phase_index(manifest.phases, completed_phase_name)
    if phase_index is None:
        raise ContinuousRefactorError(
            f"Cannot advance unknown phase {completed_phase_name!r}"
        )
    next_index = phase_index + 1
    if next_index >= len(manifest.phases):
        return None
    return manifest.phases[next_index].name


# ---------------------------------------------------------------------------
# Manifest I/O
# ---------------------------------------------------------------------------


def _require_status(raw_status: object) -> MigrationStatus:
    if not isinstance(raw_status, str):
        raise ContinuousRefactorError(
            f"Migration status must be a string: {raw_status!r}"
        )
    status = raw_status
    if status not in _VALID_STATUSES:
        raise ContinuousRefactorError(f"Unknown migration status: {status!r}")
    return cast(MigrationStatus, status)


def _require_mapping(value: object, *, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ContinuousRefactorError(
            f"Migration field {field!r} must be an object: {value!r}"
        )
    return value


def _require_str(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ContinuousRefactorError(
            f"Migration field {field!r} must be a string: {value!r}"
        )
    return value


def _optional_str(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    return _require_str(value, field=field)


def _require_bool(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise ContinuousRefactorError(
            f"Migration field {field!r} must be a boolean: {value!r}"
        )
    return value


def _require_phase_precondition(phase: dict[str, object], *, prefix: str) -> str:
    if "precondition" in phase:
        return _require_str(phase.get("precondition"), field=f"{prefix}.precondition")
    if "ready_when" in phase:
        return _require_str(phase.get("ready_when"), field=f"{prefix}.ready_when")
    raise ContinuousRefactorError(
        f"Migration field {prefix!r} must include 'precondition' "
        "(or legacy 'ready_when')"
    )


def _require_phase(raw_phase: object, *, index: int) -> PhaseSpec:
    phase = _require_mapping(raw_phase, field=f"phases[{index}]")
    prefix = f"phases[{index}]"
    return PhaseSpec(
        name=_require_str(phase.get("name"), field=f"{prefix}.name"),
        file=_require_str(phase.get("file"), field=f"{prefix}.file"),
        done=_require_bool(phase.get("done"), field=f"{prefix}.done"),
        precondition=_require_phase_precondition(phase, prefix=prefix),
    )


def _require_phases(raw_phases: object) -> tuple[PhaseSpec, ...]:
    if raw_phases is None:
        return ()
    if not isinstance(raw_phases, list):
        raise ContinuousRefactorError(
            f"Migration field 'phases' must be a list: {raw_phases!r}"
        )
    phases = tuple(
        _require_phase(raw_phase, index=index)
        for index, raw_phase in enumerate(raw_phases)
    )
    _require_unique_phase_names(phases)
    return phases


def _legacy_current_phase_name(
    legacy_cursor: int, phases: tuple[PhaseSpec, ...],
) -> str:
    if not phases:
        return ""
    if 0 <= legacy_cursor < len(phases):
        return phases[legacy_cursor].name
    return ""


def _require_current_phase(value: object, *, phases: tuple[PhaseSpec, ...]) -> str:
    if isinstance(value, bool):
        raise ContinuousRefactorError(
            f"Migration field 'current_phase' must be a string or legacy int: {value!r}"
        )
    if isinstance(value, str):
        if value == "":
            return ""
        if _phase_index(phases, value) is None:
            raise ContinuousRefactorError(
                f"Migration field 'current_phase' names an unknown phase: {value!r}"
            )
        return value
    if isinstance(value, int):
        return _legacy_current_phase_name(value, phases)
    raise ContinuousRefactorError(
        f"Migration field 'current_phase' must be a string or legacy int: {value!r}"
    )


def load_manifest(path: Path) -> MigrationManifest:
    raw = _require_mapping(
        json.loads(path.read_text(encoding="utf-8")), field="manifest"
    )
    status = _require_status(raw.get("status"))
    phases = _require_phases(raw.get("phases"))
    return MigrationManifest(
        name=_require_str(raw.get("name"), field="name"),
        created_at=_require_str(raw.get("created_at"), field="created_at"),
        last_touch=_require_str(raw.get("last_touch"), field="last_touch"),
        wake_up_on=_optional_str(raw.get("wake_up_on"), field="wake_up_on"),
        awaiting_human_review=_require_bool(
            raw.get("awaiting_human_review", False), field="awaiting_human_review"
        ),
        status=status,
        current_phase=_require_current_phase(
            raw.get("current_phase"), phases=phases,
        ),
        phases=phases,
        human_review_reason=_optional_str(
            raw.get("human_review_reason"), field="human_review_reason"
        ),
        cooldown_until=_optional_str(
            raw.get("cooldown_until"), field="cooldown_until"
        ),
    )


def save_manifest(manifest: MigrationManifest, path: Path) -> None:
    _require_status(manifest.status)
    _require_unique_phase_names(manifest.phases)
    if manifest.current_phase and _phase_index(
        manifest.phases, manifest.current_phase,
    ) is None:
        raise ContinuousRefactorError(
            f"Cannot save manifest with unknown current phase {manifest.current_phase!r}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(manifest)
    content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


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
