from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.migrations import (
    advance_phase_cursor,
    MigrationManifest,
    PhaseSpec,
    approaches_dir,
    complete_manifest_phase,
    MIGRATION_STATUSES,
    intentional_skips_dir,
    has_executable_phase,
    load_manifest,
    migration_root,
    save_manifest,
)

def _random_phase(rng: random.Random, index: int) -> PhaseSpec:
    name = "".join(rng.choices("abcdefghijklmnop", k=rng.randint(3, 10)))
    return PhaseSpec(
        name=name,
        file=f"phase-{index}-{name}.md",
        done=rng.choice([True, False]),
        precondition="".join(rng.choices("abcdefghijklmnop ", k=rng.randint(5, 30))),
    )


def _random_manifest(rng: random.Random) -> MigrationManifest:
    num_phases = rng.randint(1, 8)
    phases = tuple(_random_phase(rng, i) for i in range(num_phases))
    current_phase = rng.choice(phases).name
    return MigrationManifest(
        name="".join(rng.choices("abcdef-", k=rng.randint(5, 15))),
        created_at=f"2025-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}T00:00:00.000+00:00",
        last_touch=f"2025-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}T12:00:00.000+00:00",
        wake_up_on=rng.choice([None, "2025-06-01T00:00:00.000+00:00"]),
        awaiting_human_review=rng.choice([True, False]),
        status=rng.choice(MIGRATION_STATUSES),
        current_phase=current_phase,
        phases=phases,
        cooldown_until=rng.choice([None, "2025-06-01T06:00:00.000+00:00"]),
    )


def _write_manifest_payload(
    tmp_path: Path, slug: str, payload: dict[str, object],
) -> Path:
    path = tmp_path / slug / "manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _phase_payload(
    *,
    name: str = "setup",
    file: str = "phase-0-setup.md",
    done: bool = False,
    precondition: str | None = "always",
    ready_when: str | None = None,
    required_effort: str | None = None,
    effort_reason: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"name": name, "file": file, "done": done}
    if precondition is not None:
        payload["precondition"] = precondition
    if ready_when is not None:
        payload["ready_when"] = ready_when
    if required_effort is not None:
        payload["required_effort"] = required_effort
    if effort_reason is not None:
        payload["effort_reason"] = effort_reason
    return payload


def _manifest_payload(
    *,
    current_phase: object = "setup",
    phases: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "name": "codec-contract",
        "created_at": "2025-01-01T00:00:00.000+00:00",
        "last_touch": "2025-01-01T00:00:00.000+00:00",
        "status": "ready",
        "current_phase": current_phase,
        "phases": [_phase_payload()] if phases is None else phases,
    }


# ---------------------------------------------------------------------------
# Roundtrip (property-style)
# ---------------------------------------------------------------------------

def test_manifest_roundtrip_property(tmp_path: Path) -> None:
    rng = random.Random(42)
    for _ in range(20):
        manifest = _random_manifest(rng)
        path = tmp_path / manifest.name / "manifest.json"
        save_manifest(manifest, path)
        loaded = load_manifest(path)
        assert loaded == manifest


def test_manifest_roundtrip_preserves_phase_effort_metadata(tmp_path: Path) -> None:
    manifest = MigrationManifest(
        name="effort-metadata",
        created_at="2025-01-01T00:00:00.000+00:00",
        last_touch="2025-01-01T00:00:00.000+00:00",
        wake_up_on=None,
        awaiting_human_review=False,
        status="ready",
        current_phase="setup",
        phases=(
            PhaseSpec(
                name="setup",
                file="phase-0-setup.md",
                done=False,
                precondition="always",
                required_effort="high",
                effort_reason="cross-module risk",
            ),
            PhaseSpec(
                name="finish",
                file="phase-1-finish.md",
                done=False,
                precondition="setup done",
            ),
        ),
    )
    path = tmp_path / "effort-metadata" / "manifest.json"

    save_manifest(manifest, path)

    assert load_manifest(path) == manifest


def test_load_manifest_defaults_missing_phase_effort_metadata(tmp_path: Path) -> None:
    loaded = load_manifest(
        _write_manifest_payload(tmp_path, "legacy-effort", _manifest_payload())
    )

    assert loaded.phases[0].required_effort is None
    assert loaded.phases[0].effort_reason is None


def test_load_manifest_rejects_unknown_required_effort(tmp_path: Path) -> None:
    path = _write_manifest_payload(
        tmp_path,
        "bad-effort",
        _manifest_payload(
            phases=[_phase_payload(required_effort="extreme")],
        ),
    )

    with pytest.raises(ContinuousRefactorError, match="phases\\[0\\]\\.required_effort"):
        load_manifest(path)


def test_has_executable_phase_rejects_invalid_phase_names() -> None:
    manifest_zero_phase = MigrationManifest(
        name="empty-phases",
        created_at="2025-01-01T00:00:00.000+00:00",
        last_touch="2025-01-01T00:00:00.000+00:00",
        wake_up_on=None,
        awaiting_human_review=False,
        status="ready",
        current_phase="",
        phases=(),
    )
    manifest_missing_phase = MigrationManifest(
        name="missing-phase",
        created_at="2025-01-01T00:00:00.000+00:00",
        last_touch="2025-01-01T00:00:00.000+00:00",
        wake_up_on=None,
        awaiting_human_review=False,
        status="ready",
        current_phase="missing",
        phases=(
            PhaseSpec(name="setup", file="phase-0-setup.md", done=False, precondition="always"),
        ),
    )
    manifest_valid = MigrationManifest(
        name="valid-phase",
        created_at="2025-01-01T00:00:00.000+00:00",
        last_touch="2025-01-01T00:00:00.000+00:00",
        wake_up_on=None,
        awaiting_human_review=False,
        status="ready",
        current_phase="setup",
        phases=(
            PhaseSpec(
                name="setup", file="phase-0-setup.md", done=False, precondition="always"
            ),
        ),
    )

    assert has_executable_phase(manifest_zero_phase) is False
    assert has_executable_phase(manifest_missing_phase) is False
    assert has_executable_phase(manifest_valid) is True


# ---------------------------------------------------------------------------
# Phase completion
# ---------------------------------------------------------------------------

def test_complete_manifest_phase_advances_to_next_phase() -> None:
    completed_at = "2026-04-22T12:00:00.000+00:00"
    manifest = MigrationManifest(
        name="phase-completion",
        created_at="2026-04-22T00:00:00.000+00:00",
        last_touch="2026-04-22T06:00:00.000+00:00",
        wake_up_on="2026-04-29T06:00:00.000+00:00",
        awaiting_human_review=True,
        human_review_reason="needs review",
        status="in-progress",
        current_phase="setup",
        phases=(
            PhaseSpec(
                name="setup",
                file="phase-0-setup.md",
                done=False,
                precondition="always",
            ),
            PhaseSpec(
                name="migrate",
                file="phase-1-migrate.md",
                done=False,
                precondition="setup done",
            ),
        ),
        cooldown_until="2026-04-22T12:00:00.000+00:00",
    )

    completed = complete_manifest_phase(manifest, "setup", completed_at)

    assert completed.phases[0].done is True
    assert completed.phases[1].done is False
    assert completed.current_phase == "migrate"
    assert completed.status == "in-progress"
    assert completed.last_touch == completed_at
    assert completed.wake_up_on is None
    assert completed.awaiting_human_review is False
    assert completed.human_review_reason is None
    assert completed.cooldown_until is None


def test_complete_manifest_phase_marks_final_phase_done() -> None:
    completed_at = "2026-04-22T12:00:00.000+00:00"
    manifest = MigrationManifest(
        name="phase-completion",
        created_at="2026-04-22T00:00:00.000+00:00",
        last_touch="2026-04-22T06:00:00.000+00:00",
        wake_up_on=None,
        awaiting_human_review=False,
        status="in-progress",
        current_phase="migrate",
        phases=(
            PhaseSpec(
                name="setup",
                file="phase-0-setup.md",
                done=True,
                precondition="always",
            ),
            PhaseSpec(
                name="migrate",
                file="phase-1-migrate.md",
                done=False,
                precondition="setup done",
            ),
        ),
    )

    completed = complete_manifest_phase(manifest, "migrate", completed_at)

    assert completed.phases[0].done is True
    assert completed.phases[1].done is True
    assert completed.current_phase == ""
    assert completed.status == "done"
    assert completed.last_touch == completed_at


def test_advance_phase_cursor_returns_next_phase_name() -> None:
    manifest = MigrationManifest(
        name="phase-cursor",
        created_at="2026-04-22T00:00:00.000+00:00",
        last_touch="2026-04-22T06:00:00.000+00:00",
        wake_up_on=None,
        awaiting_human_review=False,
        status="in-progress",
        current_phase="setup",
        phases=(
            PhaseSpec(
                name="setup",
                file="phase-0-setup.md",
                done=True,
                precondition="always",
            ),
            PhaseSpec(
                name="migrate",
                file="phase-1-migrate.md",
                done=False,
                precondition="setup done",
            ),
        ),
    )

    assert advance_phase_cursor(manifest, "setup") == "migrate"
    assert advance_phase_cursor(manifest, "migrate") is None


def test_complete_manifest_phase_rejects_unknown_phase() -> None:
    manifest = MigrationManifest(
        name="phase-completion",
        created_at="2026-04-22T00:00:00.000+00:00",
        last_touch="2026-04-22T06:00:00.000+00:00",
        wake_up_on=None,
        awaiting_human_review=False,
        status="in-progress",
        current_phase="setup",
        phases=(
            PhaseSpec(
                name="setup",
                file="phase-0-setup.md",
                done=False,
                precondition="always",
            ),
        ),
    )

    with pytest.raises(ContinuousRefactorError, match="Cannot complete unknown phase"):
        complete_manifest_phase(
            manifest,
            "missing",
            "2026-04-22T12:00:00.000+00:00",
        )


# ---------------------------------------------------------------------------
# Atomic write — no .tmp files left behind
# ---------------------------------------------------------------------------

def test_save_manifest_no_tmp_files(tmp_path: Path) -> None:
    manifest = MigrationManifest(
        name="atomic-test",
        created_at="2025-01-01T00:00:00.000+00:00",
        last_touch="2025-01-01T00:00:00.000+00:00",
        wake_up_on=None,
        awaiting_human_review=False,
        status="planning",
        current_phase="setup",
        phases=(
            PhaseSpec(name="setup", file="phase-0-setup.md", done=False, precondition="always"),
        ),
    )
    out_dir = tmp_path / "atomic"
    path = out_dir / "manifest.json"
    save_manifest(manifest, path)

    tmp_files = list(out_dir.glob("*.tmp"))
    assert tmp_files == []
    assert path.exists()


def test_save_manifest_removes_tmp_file_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = MigrationManifest(
        name="atomic-test",
        created_at="2025-01-01T00:00:00.000+00:00",
        last_touch="2025-01-01T00:00:00.000+00:00",
        wake_up_on=None,
        awaiting_human_review=False,
        status="planning",
        current_phase="setup",
        phases=(
            PhaseSpec(name="setup", file="phase-0-setup.md", done=False, precondition="always"),
        ),
    )
    path = tmp_path / "atomic-failure" / "manifest.json"
    path.parent.mkdir(parents=True)
    original_content = '{"name": "old"}\n'
    path.write_text(original_content, encoding="utf-8")

    def fail_replace(self: Path, target: Path) -> Path:
        raise OSError(f"cannot replace {target} from {self}")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(
        ContinuousRefactorError, match=f"Could not save manifest {path}",
    ) as exc_info:
        save_manifest(manifest, path)

    assert isinstance(exc_info.value.__cause__, OSError)
    assert path.read_text(encoding="utf-8") == original_content
    assert list(path.parent.glob("*.tmp")) == []


# ---------------------------------------------------------------------------
# Boundary errors and schema rejection
# ---------------------------------------------------------------------------

def test_load_manifest_wraps_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "malformed" / "manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text("{", encoding="utf-8")

    with pytest.raises(
        ContinuousRefactorError, match=f"Could not parse manifest {path}",
    ) as exc_info:
        load_manifest(path)

    assert isinstance(exc_info.value.__cause__, json.JSONDecodeError)


def test_load_manifest_wraps_filesystem_read_failure(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.mkdir()

    with pytest.raises(
        ContinuousRefactorError, match=f"Could not load manifest {path}",
    ) as exc_info:
        load_manifest(path)

    assert isinstance(exc_info.value.__cause__, OSError)


def test_load_manifest_rejects_unknown_status(tmp_path: Path) -> None:
    path = tmp_path / "bad" / "manifest.json"
    path.parent.mkdir(parents=True)
    payload = {
        "name": "bad-migration",
        "created_at": "2025-01-01T00:00:00.000+00:00",
        "last_touch": "2025-01-01T00:00:00.000+00:00",
        "status": "exploded",
        "current_phase": "",
        "phases": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        ContinuousRefactorError, match="Unknown migration status",
    ) as exc_info:
        load_manifest(path)

    assert exc_info.value.__cause__ is None


def test_save_manifest_rejects_unknown_status_before_writing(tmp_path: Path) -> None:
    path = tmp_path / "bad-save" / "manifest.json"
    manifest = MigrationManifest(
        name="bad-migration",
        created_at="2025-01-01T00:00:00.000+00:00",
        last_touch="2025-01-01T00:00:00.000+00:00",
        wake_up_on=None,
        awaiting_human_review=False,
        status="exploded",
        current_phase="setup",
        phases=(
            PhaseSpec(
                name="setup",
                file="phase-0-setup.md",
                done=False,
                precondition="always",
            ),
        ),
    )

    with pytest.raises(ContinuousRefactorError, match="Unknown migration status"):
        save_manifest(manifest, path)

    assert not path.exists()
    assert not path.parent.exists()


def test_load_manifest_rejects_non_mapping_payload(tmp_path: Path) -> None:
    path = tmp_path / "bad-mapping" / "manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ContinuousRefactorError, match="must be an object"):
        load_manifest(path)


def test_load_manifest_rejects_invalid_phases_field(tmp_path: Path) -> None:
    path = tmp_path / "bad-phases" / "manifest.json"
    path.parent.mkdir(parents=True)
    payload = {
        "name": "bad-migration",
        "created_at": "2025-01-01T00:00:00.000+00:00",
        "last_touch": "2025-01-01T00:00:00.000+00:00",
        "status": "planning",
        "current_phase": "",
        "phases": {"bad": True},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ContinuousRefactorError, match="must be a list"):
        load_manifest(path)


def test_load_manifest_rejects_non_mapping_phase_entry(tmp_path: Path) -> None:
    path = tmp_path / "bad-phase-entry" / "manifest.json"
    path.parent.mkdir(parents=True)
    payload = {
        "name": "bad-migration",
        "created_at": "2025-01-01T00:00:00.000+00:00",
        "last_touch": "2025-01-01T00:00:00.000+00:00",
        "status": "planning",
        "current_phase": "",
        "phases": ["not-a-phase"],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ContinuousRefactorError, match="must be an object"):
        load_manifest(path)


def test_load_manifest_rejects_missing_required_field(tmp_path: Path) -> None:
    path = tmp_path / "missing-field" / "manifest.json"
    path.parent.mkdir(parents=True)
    payload = {
        "created_at": "2025-01-01T00:00:00.000+00:00",
        "last_touch": "2025-01-01T00:00:00.000+00:00",
        "status": "planning",
        "current_phase": "",
        "phases": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ContinuousRefactorError, match="must be a string"):
        load_manifest(path)


def test_load_manifest_rejects_non_string_status(tmp_path: Path) -> None:
    path = tmp_path / "bad-type" / "manifest.json"
    path.parent.mkdir(parents=True)
    payload = {
        "name": "bad-migration",
        "created_at": "2025-01-01T00:00:00.000+00:00",
        "last_touch": "2025-01-01T00:00:00.000+00:00",
        "status": ["planning"],
        "current_phase": "",
        "phases": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ContinuousRefactorError, match="Migration status must be a string"):
        load_manifest(path)


def test_load_manifest_rejects_bool_current_phase(tmp_path: Path) -> None:
    path = tmp_path / "bool-current-phase" / "manifest.json"
    path.parent.mkdir(parents=True)
    payload = {
        "name": "bad-migration",
        "created_at": "2025-01-01T00:00:00.000+00:00",
        "last_touch": "2025-01-01T00:00:00.000+00:00",
        "status": "planning",
        "current_phase": True,
        "phases": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        ContinuousRefactorError, match="must be a string or legacy int",
    ):
        load_manifest(path)


def test_load_manifest_accepts_legacy_ready_when_as_precondition(
    tmp_path: Path,
) -> None:
    path = _write_manifest_payload(
        tmp_path,
        "legacy-ready-when",
        _manifest_payload(
            phases=[
                _phase_payload(precondition=None, ready_when="previous phase done"),
            ],
        ),
    )

    loaded = load_manifest(path)

    assert loaded.phases[0].precondition == "previous phase done"


def test_load_manifest_prefers_precondition_over_legacy_ready_when(
    tmp_path: Path,
) -> None:
    path = _write_manifest_payload(
        tmp_path,
        "precondition-precedence",
        _manifest_payload(
            phases=[
                _phase_payload(
                    precondition="new contract",
                    ready_when="legacy contract",
                ),
            ],
        ),
    )

    loaded = load_manifest(path)

    assert loaded.phases[0].precondition == "new contract"


def test_load_manifest_rejects_phase_without_readiness_field(
    tmp_path: Path,
) -> None:
    path = _write_manifest_payload(
        tmp_path,
        "missing-phase-readiness",
        _manifest_payload(phases=[_phase_payload(precondition=None)]),
    )

    with pytest.raises(ContinuousRefactorError, match="must include 'precondition'"):
        load_manifest(path)


def test_load_manifest_accepts_empty_current_phase_with_phases(
    tmp_path: Path,
) -> None:
    path = _write_manifest_payload(
        tmp_path,
        "empty-current-phase",
        _manifest_payload(current_phase=""),
    )

    loaded = load_manifest(path)

    assert loaded.current_phase == ""
    assert loaded.phases[0].name == "setup"


def test_load_manifest_maps_legacy_integer_cursor_to_phase_name(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy-current-phase" / "manifest.json"
    path.parent.mkdir(parents=True)
    payload = {
        "name": "legacy-migration",
        "created_at": "2025-01-01T00:00:00.000+00:00",
        "last_touch": "2025-01-01T00:00:00.000+00:00",
        "status": "ready",
        "current_phase": 1,
        "phases": [
            {"name": "setup", "file": "phase-1-setup.md", "done": True, "ready_when": "always"},
            {"name": "migrate", "file": "phase-2-migrate.md", "done": False, "ready_when": "setup complete"},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_manifest(path)

    assert loaded.current_phase == "migrate"
    assert loaded.phases[0].precondition == "always"
    assert loaded.phases[1].precondition == "setup complete"


def test_load_manifest_maps_out_of_range_legacy_integer_cursor_to_empty(
    tmp_path: Path,
) -> None:
    path = _write_manifest_payload(
        tmp_path,
        "out-of-range-current-phase",
        _manifest_payload(current_phase=7),
    )

    loaded = load_manifest(path)

    assert loaded.current_phase == ""


def test_load_manifest_maps_legacy_integer_cursor_without_phases_to_empty(
    tmp_path: Path,
) -> None:
    path = _write_manifest_payload(
        tmp_path,
        "integer-current-phase-no-phases",
        _manifest_payload(current_phase=0, phases=[]),
    )

    loaded = load_manifest(path)

    assert loaded.current_phase == ""
    assert loaded.phases == ()


def test_load_manifest_rejects_unknown_string_current_phase(
    tmp_path: Path,
) -> None:
    path = _write_manifest_payload(
        tmp_path,
        "unknown-current-phase",
        _manifest_payload(current_phase="missing"),
    )

    with pytest.raises(ContinuousRefactorError, match="names an unknown phase"):
        load_manifest(path)


def test_save_manifest_rejects_unknown_current_phase_before_writing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "unknown-current-phase-save" / "manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"name": "old"}\n', encoding="utf-8")
    manifest = MigrationManifest(
        name="unknown-current-phase-save",
        created_at="2025-01-01T00:00:00.000+00:00",
        last_touch="2025-01-01T00:00:00.000+00:00",
        wake_up_on=None,
        awaiting_human_review=False,
        status="ready",
        current_phase="missing",
        phases=(
            PhaseSpec(
                name="setup",
                file="phase-0-setup.md",
                done=False,
                precondition="always",
            ),
        ),
    )

    with pytest.raises(
        ContinuousRefactorError, match="unknown current phase 'missing'",
    ):
        save_manifest(manifest, path)

    assert path.read_text(encoding="utf-8") == '{"name": "old"}\n'
    assert list(path.parent.glob("*.tmp")) == []


def test_load_manifest_rejects_duplicate_phase_names(tmp_path: Path) -> None:
    path = tmp_path / "duplicate-phases" / "manifest.json"
    path.parent.mkdir(parents=True)
    payload = {
        "name": "duplicate-migration",
        "created_at": "2025-01-01T00:00:00.000+00:00",
        "last_touch": "2025-01-01T00:00:00.000+00:00",
        "status": "ready",
        "current_phase": "setup",
        "phases": [
            {"name": "setup", "file": "phase-1-setup.md", "done": False, "precondition": "always"},
            {"name": "setup", "file": "phase-2-setup.md", "done": False, "precondition": "again"},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        ContinuousRefactorError, match="Duplicate phase names are not allowed",
    ):
        load_manifest(path)


def test_save_manifest_rejects_duplicate_phase_names_before_replacing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "duplicate-save" / "manifest.json"
    original = MigrationManifest(
        name="duplicate-save",
        created_at="2025-01-01T00:00:00.000+00:00",
        last_touch="2025-01-01T00:00:00.000+00:00",
        wake_up_on=None,
        awaiting_human_review=False,
        status="ready",
        current_phase="setup",
        phases=(
            PhaseSpec(
                name="setup",
                file="phase-0-setup.md",
                done=False,
                precondition="always",
            ),
        ),
    )
    duplicate = MigrationManifest(
        name="duplicate-save",
        created_at="2025-01-01T00:00:00.000+00:00",
        last_touch="2025-01-01T00:00:00.000+00:00",
        wake_up_on=None,
        awaiting_human_review=False,
        status="ready",
        current_phase="setup",
        phases=(
            PhaseSpec(
                name="setup",
                file="phase-0-setup.md",
                done=False,
                precondition="always",
            ),
            PhaseSpec(
                name="setup",
                file="phase-1-setup.md",
                done=False,
                precondition="again",
            ),
        ),
    )
    save_manifest(original, path)
    original_content = path.read_text(encoding="utf-8")

    with pytest.raises(
        ContinuousRefactorError, match="Duplicate phase names are not allowed",
    ):
        save_manifest(duplicate, path)

    assert path.read_text(encoding="utf-8") == original_content
    assert list(path.parent.glob("*.tmp")) == []


# ---------------------------------------------------------------------------
# Default values for optional fields
# ---------------------------------------------------------------------------

def test_load_manifest_defaults_optional_fields(tmp_path: Path) -> None:
    path = tmp_path / "defaults" / "manifest.json"
    path.parent.mkdir(parents=True)
    payload = {
        "name": "minimal",
        "created_at": "2025-01-01T00:00:00.000+00:00",
        "last_touch": "2025-01-01T00:00:00.000+00:00",
        "status": "planning",
        "current_phase": "init",
        "phases": [
            {"name": "init", "file": "phase-0-init.md", "done": False, "precondition": "always"},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_manifest(path)

    assert loaded.wake_up_on is None
    assert loaded.awaiting_human_review is False
    assert loaded.cooldown_until is None


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def test_migration_root() -> None:
    root = migration_root(Path("/live"), "my-migration")
    assert root == Path("/live/my-migration")


def test_approaches_dir_returns_expected() -> None:
    result = approaches_dir(Path("/live"), "mig")
    assert result == Path("/live/mig/approaches")


def test_intentional_skips_dir_returns_expected() -> None:
    result = intentional_skips_dir(Path("/live"))
    assert result == Path("/live/__intentional_skips__")


# ---------------------------------------------------------------------------
# JSON output format
# ---------------------------------------------------------------------------

def test_load_manifest_reads_cooldown_until(tmp_path: Path) -> None:
    path = tmp_path / "cooldown" / "manifest.json"
    path.parent.mkdir(parents=True)
    payload = {
        "name": "cooldown-migration",
        "created_at": "2025-01-01T00:00:00.000+00:00",
        "last_touch": "2025-01-01T01:00:00.000+00:00",
        "wake_up_on": None,
        "cooldown_until": "2025-01-01T07:00:00.000+00:00",
        "status": "ready",
        "current_phase": "setup",
        "phases": [
            {"name": "setup", "file": "phase-0-setup.md", "done": False, "precondition": "always"},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_manifest(path)

    assert loaded.cooldown_until == "2025-01-01T07:00:00.000+00:00"


# ---------------------------------------------------------------------------
# JSON output format
# ---------------------------------------------------------------------------

def test_save_manifest_uses_indent_and_sorted_keys(tmp_path: Path) -> None:
    manifest = MigrationManifest(
        name="format-check",
        created_at="2025-01-01T00:00:00.000+00:00",
        last_touch="2025-01-01T00:00:00.000+00:00",
        wake_up_on=None,
        awaiting_human_review=False,
        status="ready",
        current_phase="",
        phases=(
            PhaseSpec(
                name="setup",
                file="phase-0-setup.md",
                done=False,
                precondition="always",
            ),
        ),
    )
    path = tmp_path / "fmt" / "manifest.json"
    save_manifest(manifest, path)

    raw = path.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    expected = json.dumps(parsed, indent=2, sort_keys=True) + "\n"
    assert raw == expected
    assert parsed["phases"][0]["precondition"] == "always"
    assert "ready_when" not in parsed["phases"][0]
