from __future__ import annotations

import json
from dataclasses import asdict
from typing import cast

from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.effort import EffortTier, require_effort_tier
from continuous_refactoring.migrations import (
    MIGRATION_STATUSES,
    MigrationManifest,
    MigrationStatus,
    PhaseSpec,
)

__all__ = ("decode_manifest_payload", "encode_manifest_payload")

_VALID_STATUSES: frozenset[str] = frozenset(
    cast(tuple[str, ...], MIGRATION_STATUSES)
)


def _require_status(raw_status: object) -> MigrationStatus:
    if not isinstance(raw_status, str):
        raise ContinuousRefactorError(
            f"Migration status must be a string: {raw_status!r}"
        )
    if raw_status not in _VALID_STATUSES:
        raise ContinuousRefactorError(f"Unknown migration status: {raw_status!r}")
    return cast(MigrationStatus, raw_status)


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
    required_effort_raw = phase.get("required_effort")
    required_effort: EffortTier | None = None
    if required_effort_raw is not None:
        required_effort = require_effort_tier(
            required_effort_raw,
            field=f"{prefix}.required_effort",
        )
    return PhaseSpec(
        name=_require_str(phase.get("name"), field=f"{prefix}.name"),
        file=_require_str(phase.get("file"), field=f"{prefix}.file"),
        done=_require_bool(phase.get("done"), field=f"{prefix}.done"),
        precondition=_require_phase_precondition(phase, prefix=prefix),
        required_effort=required_effort,
        effort_reason=_optional_str(
            phase.get("effort_reason"), field=f"{prefix}.effort_reason"
        ),
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
        if not any(phase.name == value for phase in phases):
            raise ContinuousRefactorError(
                f"Migration field 'current_phase' names an unknown phase: {value!r}"
            )
        return value
    if isinstance(value, int):
        return _legacy_current_phase_name(value, phases)
    raise ContinuousRefactorError(
        f"Migration field 'current_phase' must be a string or legacy int: {value!r}"
    )


def decode_manifest_payload(raw_payload: object) -> MigrationManifest:
    raw = _require_mapping(raw_payload, field="manifest")
    phases = _require_phases(raw.get("phases"))
    return MigrationManifest(
        name=_require_str(raw.get("name"), field="name"),
        created_at=_require_str(raw.get("created_at"), field="created_at"),
        last_touch=_require_str(raw.get("last_touch"), field="last_touch"),
        wake_up_on=_optional_str(raw.get("wake_up_on"), field="wake_up_on"),
        awaiting_human_review=_require_bool(
            raw.get("awaiting_human_review", False), field="awaiting_human_review"
        ),
        status=_require_status(raw.get("status")),
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


def encode_manifest_payload(manifest: MigrationManifest) -> str:
    _require_status(manifest.status)
    _require_unique_phase_names(manifest.phases)
    if manifest.current_phase and not any(
        phase.name == manifest.current_phase for phase in manifest.phases
    ):
        raise ContinuousRefactorError(
            f"Cannot save manifest with unknown current phase {manifest.current_phase!r}"
        )
    return json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n"
