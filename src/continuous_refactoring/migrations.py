from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, cast, get_args

from continuous_refactoring.artifacts import ContinuousRefactorError

__all__ = [
    "MigrationManifest",
    "PhaseSpec",
    "MIGRATION_STATUSES",
    "approaches_dir",
    "bump_last_touch",
    "eligible_now",
    "intentional_skips_dir",
    "load_manifest",
    "migration_root",
    "phase_path",
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
    ready_when: str


@dataclass(frozen=True)
class MigrationManifest:
    name: str
    created_at: str
    last_touch: str
    wake_up_on: str | None
    awaiting_human_review: bool
    status: MigrationStatus
    current_phase: int
    phases: tuple[PhaseSpec, ...]


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def migration_root(live_dir: Path, name: str) -> Path:
    return live_dir / name


def phase_path(live_dir: Path, name: str, phase: PhaseSpec) -> Path:
    return migration_root(live_dir, name) / phase.file


def approaches_dir(live_dir: Path, name: str) -> Path:
    return migration_root(live_dir, name) / "approaches"


def intentional_skips_dir(live_dir: Path) -> Path:
    return live_dir / "__intentional_skips__"


# ---------------------------------------------------------------------------
# Manifest I/O
# ---------------------------------------------------------------------------


def _coerce_status(raw_status: object) -> MigrationStatus:
    if not isinstance(raw_status, str):
        raise ContinuousRefactorError(f"Migration status must be a string: {raw_status!r}")
    if raw_status not in _VALID_STATUSES:
        raise ContinuousRefactorError(f"Unknown migration status: {raw_status!r}")
    return cast(MigrationStatus, raw_status)


def _coerce_mapping(value: object, *, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ContinuousRefactorError(
            f"Migration field {field!r} must be an object: {value!r}"
        )
    return value


def _coerce_str_field(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ContinuousRefactorError(
            f"Migration field {field!r} must be a string: {value!r}"
        )
    return value


def _coerce_bool_field(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise ContinuousRefactorError(
            f"Migration field {field!r} must be a boolean: {value!r}"
        )
    return value


def _coerce_int_field(value: object, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ContinuousRefactorError(
            f"Migration field {field!r} must be an int: {value!r}"
        )
    return value


def _coerce_optional_str_field(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    return _coerce_str_field(value, field=field)


def _coerce_phase(raw_phase: object, *, index: int) -> PhaseSpec:
    phase = _coerce_mapping(raw_phase, field=f"phases[{index}]")
    return PhaseSpec(
        name=_coerce_str_field(phase.get("name"), field=f"phases[{index}].name"),
        file=_coerce_str_field(phase.get("file"), field=f"phases[{index}].file"),
        done=_coerce_bool_field(phase.get("done"), field=f"phases[{index}].done"),
        ready_when=_coerce_str_field(
            phase.get("ready_when"), field=f"phases[{index}].ready_when"
        ),
    )


def _coerce_phases(raw_phases: object) -> tuple[PhaseSpec, ...]:
    if raw_phases is None:
        return ()
    if not isinstance(raw_phases, list):
        raise ContinuousRefactorError(
            f"Migration field 'phases' must be a list: {raw_phases!r}"
        )
    return tuple(
        _coerce_phase(raw_phase, index=index) for index, raw_phase in enumerate(raw_phases)
    )


def load_manifest(path: Path) -> MigrationManifest:
    raw = _coerce_mapping(
        json.loads(path.read_text(encoding="utf-8")), field="manifest"
    )
    status = _coerce_status(raw.get("status"))
    phases = _coerce_phases(raw.get("phases"))
    return MigrationManifest(
        name=_coerce_str_field(raw.get("name"), field="name"),
        created_at=_coerce_str_field(raw.get("created_at"), field="created_at"),
        last_touch=_coerce_str_field(raw.get("last_touch"), field="last_touch"),
        wake_up_on=_coerce_optional_str_field(
            raw.get("wake_up_on"), field="wake_up_on"
        ),
        awaiting_human_review=_coerce_bool_field(
            raw.get("awaiting_human_review", False), field="awaiting_human_review"
        ),
        status=status,
        current_phase=_coerce_int_field(raw.get("current_phase"), field="current_phase"),
        phases=phases,
    )


def save_manifest(manifest: MigrationManifest, path: Path) -> None:
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
    elapsed = now - datetime.fromisoformat(manifest.last_touch)
    if elapsed < _COOLDOWN:
        return False
    if manifest.wake_up_on is None:
        return True
    return datetime.fromisoformat(manifest.wake_up_on) <= now or elapsed >= _STALE


def bump_last_touch(manifest: MigrationManifest, now: datetime) -> MigrationManifest:
    return replace(manifest, last_touch=now.isoformat(timespec="milliseconds"))
