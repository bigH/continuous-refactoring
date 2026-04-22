"""Migration tick orchestration."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from continuous_refactoring.artifacts import RunArtifacts
    from continuous_refactoring.migrations import MigrationManifest, PhaseSpec
    from continuous_refactoring.phases import ExecutePhaseOutcome

__all__ = [
    "enumerate_eligible_manifests",
    "try_migration_tick",
]

from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.decisions import (
    DecisionRecord,
    RouteOutcome,
    error_failure_kind,
    sanitize_text,
)
from continuous_refactoring.git import get_head_sha
from continuous_refactoring.migrations import (
    bump_last_touch,
    eligible_now,
    has_executable_phase,
    load_manifest,
    phase_file_reference,
    resolve_current_phase,
    save_manifest,
)
from continuous_refactoring.phases import check_phase_ready, execute_phase


class _FinalizeCommit(Protocol):
    def __call__(
        self,
        repo_root: Path,
        head_before: str,
        commit_message: str,
        *,
        artifacts: RunArtifacts,
        attempt: int,
        phase: str,
    ) -> str | None:
        ...


def enumerate_eligible_manifests(
    live_dir: Path, now: datetime,
) -> list[tuple[MigrationManifest, Path]]:
    if not live_dir.is_dir():
        return []
    candidates: list[tuple[MigrationManifest, Path]] = []
    for entry in sorted(live_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("__"):
            continue
        manifest_path = entry / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = load_manifest(manifest_path)
        if manifest.status not in ("ready", "in-progress"):
            continue
        if not has_executable_phase(manifest):
            continue
        if not eligible_now(manifest, now):
            continue
        candidates.append((manifest, manifest_path))
    candidates.sort(key=lambda pair: datetime.fromisoformat(pair[0].created_at))
    return candidates


def try_migration_tick(
    live_dir: Path,
    taste: str,
    repo_root: Path,
    artifacts: RunArtifacts,
    *,
    agent: str,
    model: str,
    effort: str,
    timeout: int | None,
    commit_message_prefix: str,
    validation_command: str,
    max_attempts: int | None,
    attempt: int,
    finalize_commit: _FinalizeCommit,
) -> tuple[RouteOutcome, DecisionRecord | None]:
    now = datetime.now(timezone.utc)
    candidates = enumerate_eligible_manifests(live_dir, now)
    deferred_record: DecisionRecord | None = None

    for manifest, manifest_path in candidates:
        phase = resolve_current_phase(manifest)
        target_label = _target_label(manifest, phase)
        try:
            verdict, reason = check_phase_ready(
                phase,
                manifest,
                repo_root,
                artifacts,
                taste=taste,
                attempt=attempt,
                retry=1,
                agent=agent,
                model=model,
                effort=effort,
                timeout=timeout,
            )
        except ContinuousRefactorError as error:
            return "abandon", _ready_check_failure_record(error, repo_root, target_label)

        if verdict == "yes":
            head_before = get_head_sha(repo_root)
            outcome = execute_phase(
                phase,
                manifest,
                taste,
                repo_root,
                live_dir,
                artifacts,
                attempt=attempt,
                retry=1,
                agent=agent,
                model=model,
                effort=effort,
                timeout=timeout,
                validation_command=validation_command,
                max_attempts=max_attempts,
            )

            if outcome.status != "failed":
                finalize_commit(
                    repo_root,
                    head_before,
                    f"{commit_message_prefix}: migration/{manifest.name}"
                    f"/{phase_file_reference(phase)}",
                    artifacts=artifacts,
                    attempt=attempt,
                    phase="migration",
                )

            print(
                f"Migration: {outcome.status}"
                f" — {manifest.name} {phase_file_reference(phase)} ({phase.name})"
            )
            if outcome.status == "failed":
                return "abandon", _phase_failure_record(outcome, repo_root, target_label)
            return "commit", _phase_commit_record(target_label)

        save_manifest(
            _defer_manifest(manifest, now, verdict=verdict, reason=reason),
            manifest_path,
        )
        if verdict == "unverifiable":
            return "blocked", _human_review_record(reason, repo_root, target_label)
        deferred_record = _deferred_record(reason, repo_root, target_label)

    return "not-routed", deferred_record


def _target_label(manifest: MigrationManifest, phase: PhaseSpec) -> str:
    return f"{manifest.name} {phase_file_reference(phase)} ({phase.name})"


def _ready_check_failure_record(
    error: ContinuousRefactorError, repo_root: Path, target_label: str,
) -> DecisionRecord:
    summary = sanitize_text(str(error), repo_root) or str(error)
    return DecisionRecord(
        decision="abandon",
        retry_recommendation="new-target",
        target=target_label,
        call_role="phase.ready-check",
        phase_reached="phase.ready-check",
        failure_kind=error_failure_kind(str(error)),
        summary=summary,
    )


def _phase_failure_record(
    outcome: ExecutePhaseOutcome, repo_root: Path, target_label: str,
) -> DecisionRecord:
    return DecisionRecord(
        decision="abandon",
        retry_recommendation="new-target",
        target=target_label,
        call_role=outcome.call_role or "phase.execute",
        phase_reached=outcome.phase_reached or "phase.execute",
        failure_kind=outcome.failure_kind or "phase-failed",
        summary=sanitize_text(outcome.reason, repo_root) or outcome.reason,
        retry_used=outcome.retry,
    )


def _phase_commit_record(target_label: str) -> DecisionRecord:
    return DecisionRecord(
        decision="commit",
        retry_recommendation="none",
        target=target_label,
        call_role="phase.execute",
        phase_reached="phase.execute",
        failure_kind="none",
        summary="Migration phase completed successfully",
    )


def _defer_manifest(
    manifest: MigrationManifest,
    now: datetime,
    *,
    verdict: str,
    reason: str,
) -> MigrationManifest:
    updated = replace(
        bump_last_touch(manifest, now),
        cooldown_until=(now + timedelta(hours=6)).isoformat(timespec="milliseconds"),
    )
    if updated.wake_up_on is None:
        wake = (now + timedelta(days=7)).isoformat(timespec="milliseconds")
        updated = replace(updated, wake_up_on=wake)
    if verdict == "unverifiable":
        updated = replace(
            updated,
            awaiting_human_review=True,
            human_review_reason=reason,
        )
    return updated


def _human_review_record(
    reason: str, repo_root: Path, target_label: str,
) -> DecisionRecord:
    summary = sanitize_text(reason, repo_root) or "Phase requires human review"
    return DecisionRecord(
        decision="blocked",
        retry_recommendation="human-review",
        target=target_label,
        call_role="phase.ready-check",
        phase_reached="phase.ready-check",
        failure_kind="phase-ready-unverifiable",
        summary=summary,
    )


def _deferred_record(reason: str, repo_root: Path, target_label: str) -> DecisionRecord:
    return DecisionRecord(
        decision="retry",
        retry_recommendation="same-target",
        target=target_label,
        call_role="phase.ready-check",
        phase_reached="phase.ready-check",
        failure_kind="phase-ready-no",
        summary=sanitize_text(reason, repo_root) or "Migration phase not ready",
    )
