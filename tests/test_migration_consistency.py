from __future__ import annotations

from pathlib import Path

import pytest

from continuous_refactoring.migration_consistency import (
    CONSISTENCY_MODES,
    CONSISTENCY_SEVERITIES,
    MigrationConsistencyFinding,
    check_migration_consistency,
    has_blocking_consistency_findings,
    iter_visible_migration_dirs,
)
from continuous_refactoring.migrations import (
    MigrationManifest,
    PhaseSpec,
    save_manifest,
)

_PHASE = PhaseSpec(
    name="setup",
    file="phase-0-setup.md",
    done=False,
    precondition="always",
)


def _manifest(
    name: str,
    *,
    status: str = "ready",
    phase: PhaseSpec = _PHASE,
) -> MigrationManifest:
    return MigrationManifest(
        name=name,
        created_at="2025-01-01T00:00:00.000+00:00",
        last_touch="2025-01-01T00:00:00.000+00:00",
        wake_up_on=None,
        awaiting_human_review=False,
        status=status,
        current_phase=phase.name,
        phases=(phase,),
    )


def _write_migration(
    root: Path,
    slug: str,
    *,
    manifest_name: str | None = None,
    status: str = "ready",
    phase: PhaseSpec = _PHASE,
    write_plan: bool = True,
    write_phase: bool = True,
) -> Path:
    migration_dir = root / slug
    migration_dir.mkdir(parents=True)
    if write_plan:
        (migration_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")
    if write_phase:
        phase_path = migration_dir / phase.file
        phase_path.parent.mkdir(parents=True, exist_ok=True)
        phase_path.write_text("# Setup\n", encoding="utf-8")
    save_manifest(
        _manifest(manifest_name or slug, status=status, phase=phase),
        migration_dir / "manifest.json",
    )
    return migration_dir


def _codes(findings: list[MigrationConsistencyFinding]) -> set[str]:
    return {finding.code for finding in findings}


def test_visible_migration_dirs_skip_hidden_dotted_and_transaction_dirs(
    tmp_path: Path,
) -> None:
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    (live_dir / "plain-file").write_text("ignore\n", encoding="utf-8")
    (live_dir / "visible-b").mkdir()
    (live_dir / ".staged").mkdir()
    (live_dir / "__internal").mkdir()
    (live_dir / "__transactions__").mkdir()
    (live_dir / "visible-a").mkdir()

    dirs = iter_visible_migration_dirs(live_dir)

    assert [path.name for path in dirs] == ["visible-a", "visible-b"]


def test_visible_migration_dirs_skip_directory_symlinks(tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (live_dir / "real").mkdir()
    link = live_dir / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"directory symlinks unavailable: {error}")

    assert link.is_dir()
    assert [path.name for path in iter_visible_migration_dirs(live_dir)] == ["real"]


def test_consistency_reports_missing_manifest(tmp_path: Path) -> None:
    migration_dir = tmp_path / "missing-manifest"
    migration_dir.mkdir()

    findings = check_migration_consistency(migration_dir, mode="doctor")

    assert [(finding.code, finding.severity, finding.mode, finding.path) for finding in findings] == [
        (
            "missing-manifest",
            "error",
            "doctor",
            migration_dir / "manifest.json",
        )
    ]


def test_consistency_rejects_manifest_slug_mismatch(tmp_path: Path) -> None:
    migration_dir = _write_migration(
        tmp_path, "actual-slug", manifest_name="different-slug",
    )

    findings = check_migration_consistency(migration_dir, mode="execution-gate")

    assert "manifest-slug-mismatch" in _codes(findings)
    assert has_blocking_consistency_findings(findings)


def test_consistency_rejects_manifest_phase_symlink_escape(tmp_path: Path) -> None:
    migration_dir = _write_migration(tmp_path, "symlink-escape", write_phase=False)
    outside = tmp_path / "outside-phase.md"
    outside.write_text("# Outside\n", encoding="utf-8")
    try:
        (migration_dir / _PHASE.file).symlink_to(outside)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unavailable: {error}")

    findings = check_migration_consistency(migration_dir, mode="execution-gate")

    assert "phase-file-escapes-migration" in _codes(findings)
    assert has_blocking_consistency_findings(findings)


def test_consistency_reports_duplicate_phase_doc_indexes(tmp_path: Path) -> None:
    migration_dir = _write_migration(tmp_path, "duplicate-phase-index")
    (migration_dir / "phase-0-other.md").write_text("# Other\n", encoding="utf-8")

    findings = check_migration_consistency(migration_dir, mode="doctor")

    assert "duplicate-phase-doc-index" in _codes(findings)


def test_consistency_reports_manifest_phase_missing_doc(tmp_path: Path) -> None:
    migration_dir = _write_migration(tmp_path, "missing-phase-doc", write_phase=False)

    findings = check_migration_consistency(migration_dir, mode="execution-gate")

    assert "missing-phase-file" in _codes(findings)
    assert has_blocking_consistency_findings(findings)


def test_consistency_requires_plan_for_ready_and_in_progress(tmp_path: Path) -> None:
    migration_dir = _write_migration(tmp_path, "missing-plan", write_plan=False)

    execution_findings = check_migration_consistency(
        migration_dir, mode="execution-gate",
    )
    planning_findings = check_migration_consistency(
        migration_dir, mode="planning-snapshot",
    )

    assert "missing-plan" in _codes(execution_findings)
    assert "missing-plan" not in _codes(planning_findings)
    assert has_blocking_consistency_findings(execution_findings)


def test_consistency_modes_share_severity_blocking_contract(tmp_path: Path) -> None:
    info = MigrationConsistencyFinding(
        severity="info",
        mode="doctor",
        code="context",
        path=tmp_path,
        message="context",
    )
    warning = MigrationConsistencyFinding(
        severity="warning",
        mode="ready-publish",
        code="suspicious",
        path=tmp_path,
        message="suspicious",
    )
    error = MigrationConsistencyFinding(
        severity="error",
        mode="execution-gate",
        code="unsafe",
        path=tmp_path,
        message="unsafe",
    )

    assert set(CONSISTENCY_MODES) == {
        "planning-snapshot",
        "ready-publish",
        "execution-gate",
        "doctor",
    }
    assert set(CONSISTENCY_SEVERITIES) == {"info", "warning", "error"}
    assert not has_blocking_consistency_findings([info, warning])
    assert has_blocking_consistency_findings([info, warning, error])
