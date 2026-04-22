from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.migrations import (
    MigrationManifest,
    PhaseSpec,
    approaches_dir,
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


# ---------------------------------------------------------------------------
# Unknown status rejection
# ---------------------------------------------------------------------------

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

    with pytest.raises(ContinuousRefactorError, match="Unknown migration status"):
        load_manifest(path)


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
