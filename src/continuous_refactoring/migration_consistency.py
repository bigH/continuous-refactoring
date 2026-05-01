from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.migrations import MigrationManifest, load_manifest

__all__ = [
    "CONSISTENCY_MODES",
    "CONSISTENCY_SEVERITIES",
    "ConsistencyMode",
    "ConsistencySeverity",
    "MigrationConsistencyFinding",
    "check_migration_consistency",
    "has_blocking_consistency_findings",
    "iter_visible_migration_dirs",
]

ConsistencyMode = Literal[
    "planning-snapshot",
    "ready-publish",
    "execution-gate",
    "doctor",
]
ConsistencySeverity = Literal["info", "warning", "error"]

CONSISTENCY_MODES: tuple[ConsistencyMode, ...] = (
    "planning-snapshot",
    "ready-publish",
    "execution-gate",
    "doctor",
)
CONSISTENCY_SEVERITIES: tuple[ConsistencySeverity, ...] = (
    "info",
    "warning",
    "error",
)

_PHASE_DOC_RE = re.compile(r"^phase-(?P<index>\d+)-(?P<name>.+)\.md$")
_INTERNAL_MIGRATION_DIR_NAMES = frozenset(
    {
        "__intentional_skips__",
        "__transactions__",
    }
)


@dataclass(frozen=True)
class MigrationConsistencyFinding:
    severity: ConsistencySeverity
    mode: ConsistencyMode
    code: str
    path: Path
    message: str


def iter_visible_migration_dirs(live_dir: Path) -> list[Path]:
    if not live_dir.is_dir():
        return []
    return [
        child
        for child in sorted(live_dir.iterdir())
        if (
            child.is_dir()
            and not child.is_symlink()
            and _is_visible_migration_dir_name(child.name)
        )
    ]


def check_migration_consistency(
    migration_dir: Path,
    mode: ConsistencyMode,
) -> list[MigrationConsistencyFinding]:
    manifest_path = migration_dir / "manifest.json"
    findings: list[MigrationConsistencyFinding] = []
    if not manifest_path.exists():
        return [
            _finding(
                mode,
                "error",
                "missing-manifest",
                manifest_path,
                "Migration manifest is missing.",
            )
        ]

    try:
        manifest = load_manifest(manifest_path)
    except ContinuousRefactorError as error:
        return [
            _finding(
                mode,
                "error",
                "invalid-manifest",
                manifest_path,
                str(error),
            )
        ]

    if manifest.name != migration_dir.name:
        findings.append(
            _finding(
                mode,
                "error",
                "manifest-slug-mismatch",
                manifest_path,
                (
                    f"Manifest name {manifest.name!r} does not match "
                    f"directory slug {migration_dir.name!r}."
                ),
            )
        )

    findings.extend(_phase_doc_duplicate_findings(migration_dir, mode))
    findings.extend(_plan_findings(migration_dir, manifest, mode))
    findings.extend(_manifest_phase_file_findings(migration_dir, manifest, mode))
    findings.extend(_manifest_phase_metadata_findings(migration_dir, manifest, mode))
    return findings


def has_blocking_consistency_findings(
    findings: Iterable[MigrationConsistencyFinding],
) -> bool:
    return any(finding.severity == "error" for finding in findings)


def _is_visible_migration_dir_name(name: str) -> bool:
    return (
        not name.startswith(".")
        and not name.startswith("__")
        and name not in _INTERNAL_MIGRATION_DIR_NAMES
    )


def _finding(
    mode: ConsistencyMode,
    severity: ConsistencySeverity,
    code: str,
    path: Path,
    message: str,
) -> MigrationConsistencyFinding:
    return MigrationConsistencyFinding(
        severity=severity,
        mode=mode,
        code=code,
        path=path,
        message=message,
    )


def _phase_doc_duplicate_findings(
    migration_dir: Path,
    mode: ConsistencyMode,
) -> list[MigrationConsistencyFinding]:
    findings: list[MigrationConsistencyFinding] = []
    by_index: dict[int, Path] = {}
    by_name: dict[str, Path] = {}
    for path in _phase_doc_paths(migration_dir):
        match = _PHASE_DOC_RE.match(path.name)
        if match is None:
            continue
        phase_index = int(match.group("index"))
        phase_name = match.group("name")
        if phase_index in by_index:
            findings.append(
                _finding(
                    mode,
                    "error",
                    "duplicate-phase-doc-index",
                    path,
                    (
                        f"Phase doc index {phase_index} is duplicated by "
                        f"{by_index[phase_index].name!r} and {path.name!r}."
                    ),
                )
            )
        else:
            by_index[phase_index] = path
        if phase_name in by_name:
            findings.append(
                _finding(
                    mode,
                    "error",
                    "duplicate-phase-doc-name",
                    path,
                    (
                        f"Phase doc name {phase_name!r} is duplicated by "
                        f"{by_name[phase_name].name!r} and {path.name!r}."
                    ),
                )
            )
        else:
            by_name[phase_name] = path
    return findings


def _phase_doc_paths(migration_dir: Path) -> list[Path]:
    try:
        return [
            child
            for child in sorted(migration_dir.iterdir())
            if _PHASE_DOC_RE.match(child.name) is not None
        ]
    except OSError as error:
        raise ContinuousRefactorError(
            f"Could not scan migration directory {migration_dir}: {error}"
        ) from error


def _plan_findings(
    migration_dir: Path,
    manifest: MigrationManifest,
    mode: ConsistencyMode,
) -> list[MigrationConsistencyFinding]:
    if not _requires_plan(manifest, mode):
        return []
    plan_path = migration_dir / "plan.md"
    if plan_path.exists():
        return []
    return [
        _finding(
            mode,
            "error",
            "missing-plan",
            plan_path,
            "Ready and in-progress migrations require plan.md.",
        )
    ]


def _requires_plan(manifest: MigrationManifest, mode: ConsistencyMode) -> bool:
    return mode == "ready-publish" or (
        mode in ("doctor", "execution-gate")
        and manifest.status in ("ready", "in-progress")
    )


def _manifest_phase_file_findings(
    migration_dir: Path,
    manifest: MigrationManifest,
    mode: ConsistencyMode,
) -> list[MigrationConsistencyFinding]:
    findings: list[MigrationConsistencyFinding] = []
    for phase in manifest.phases:
        ref = Path(phase.file)
        if _invalid_phase_file_reference(ref):
            findings.append(
                _finding(
                    mode,
                    "error",
                    "invalid-phase-file-reference",
                    migration_dir / phase.file,
                    f"Phase file reference {phase.file!r} must stay inside the migration directory.",
                )
            )
            continue

        phase_path = migration_dir / ref
        if phase_path.is_symlink():
            findings.extend(_symlink_phase_file_findings(migration_dir, phase_path, mode))
            continue

        if not phase_path.exists():
            findings.append(
                _finding(
                    mode,
                    "error",
                    "missing-phase-file",
                    phase_path,
                    f"Manifest phase file {phase.file!r} is missing.",
                )
            )
            continue

        if not _is_inside(phase_path.resolve(), migration_dir.resolve()):
            findings.append(
                _finding(
                    mode,
                    "error",
                    "phase-file-escapes-migration",
                    phase_path,
                    f"Manifest phase file {phase.file!r} resolves outside the migration directory.",
                )
            )
            continue

        if not phase_path.is_file():
            findings.append(
                _finding(
                    mode,
                    "error",
                    "phase-file-not-regular",
                    phase_path,
                    f"Manifest phase file {phase.file!r} is not a regular file.",
                )
            )
    return findings


def _manifest_phase_metadata_findings(
    migration_dir: Path,
    manifest: MigrationManifest,
    mode: ConsistencyMode,
) -> list[MigrationConsistencyFinding]:
    if not _requires_ready_publish_metadata(manifest, mode):
        return []

    findings: list[MigrationConsistencyFinding] = []
    phase_names = {phase.name for phase in manifest.phases}
    if not phase_names:
        findings.append(
            _finding(
                mode,
                "error",
                "missing-manifest-phases",
                migration_dir / "manifest.json",
                "Ready migrations require at least one manifest phase.",
            )
        )
    elif manifest.current_phase not in phase_names:
        findings.append(
            _finding(
                mode,
                "error",
                "invalid-current-phase",
                migration_dir / "manifest.json",
                (
                    f"Current phase {manifest.current_phase!r} does not match "
                    "any manifest phase."
                ),
            )
        )

    doc_phase_names = {
        match.group("name")
        for path in _phase_doc_paths(migration_dir)
        if (match := _PHASE_DOC_RE.match(path.name)) is not None
    }
    for doc_phase_name in sorted(doc_phase_names - phase_names):
        findings.append(
            _finding(
                mode,
                "error",
                "phase-doc-not-in-manifest",
                migration_dir / f"phase-*-{doc_phase_name}.md",
                f"Phase doc {doc_phase_name!r} is not represented in manifest phases.",
            )
        )

    for phase in manifest.phases:
        phase_path = migration_dir / phase.file
        if phase_path.is_file() and not phase_path.is_symlink():
            findings.extend(_phase_doc_contract_findings(phase_path, mode))
    return findings


def _requires_ready_publish_metadata(
    manifest: MigrationManifest,
    mode: ConsistencyMode,
) -> bool:
    return mode == "ready-publish" or (
        mode == "doctor" and manifest.status in ("ready", "in-progress")
    )


def _phase_doc_contract_findings(
    phase_path: Path,
    mode: ConsistencyMode,
) -> list[MigrationConsistencyFinding]:
    try:
        content = phase_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ContinuousRefactorError(
            f"Could not read phase doc {phase_path}: {error}"
        ) from error

    findings: list[MigrationConsistencyFinding] = []
    if not re.search(r"^##\s+Precondition\s*$", content, re.IGNORECASE | re.MULTILINE):
        findings.append(
            _finding(
                mode,
                "error",
                "missing-phase-precondition",
                phase_path,
                "Phase docs require a ## Precondition section before ready publish.",
            )
        )
    if not re.search(
        r"^##\s+Definition of Done\s*$",
        content,
        re.IGNORECASE | re.MULTILINE,
    ):
        findings.append(
            _finding(
                mode,
                "error",
                "missing-phase-definition-of-done",
                phase_path,
                "Phase docs require a ## Definition of Done section before ready publish.",
            )
        )
    return findings


def _invalid_phase_file_reference(ref: Path) -> bool:
    return (
        str(ref) in ("", ".")
        or ref.is_absolute()
        or ".." in ref.parts
    )


def _symlink_phase_file_findings(
    migration_dir: Path,
    phase_path: Path,
    mode: ConsistencyMode,
) -> list[MigrationConsistencyFinding]:
    if not _is_inside(phase_path.resolve(), migration_dir.resolve()):
        return [
            _finding(
                mode,
                "error",
                "phase-file-escapes-migration",
                phase_path,
                f"Phase file symlink {phase_path.name!r} resolves outside the migration directory.",
            )
        ]
    return [
        _finding(
            mode,
            "error",
            "phase-file-not-regular",
            phase_path,
            f"Phase file {phase_path.name!r} must be a regular file, not a symlink.",
        )
    ]


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
