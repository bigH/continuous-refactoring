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
from continuous_refactoring.commit_messages import build_commit_message
from continuous_refactoring.decisions import (
    DecisionRecord,
    RouteOutcome,
    error_failure_kind,
    sanitize_text,
    sanitized_text_or,
)
from continuous_refactoring.effort import (
    EffortBudget,
    effort_exceeds,
    resolve_effort_budget,
    resolve_phase_effort,
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
from continuous_refactoring.phases import (
    ReadyVerdict,
    check_phase_ready,
    execute_phase,
)


_BASELINE_VALIDATION_UNCERTAINTY_PHRASES = (
    "baseline green",
    "baseline validation",
    "current tests pass",
    "fresh test evidence",
    "fresh validation evidence",
    "full test suite passes",
    "tests pass now",
)


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
    live_dir: Path,
    now: datetime,
    effort_budget: EffortBudget | None = None,
) -> list[tuple[MigrationManifest, Path]]:
    candidates: list[tuple[MigrationManifest, Path]] = []
    for manifest, manifest_path in _iter_candidate_manifests(live_dir):
        if _is_normally_eligible(manifest, now):
            candidates.append((manifest, manifest_path))
    if effort_budget is not None:
        seen_paths = {path for _, path in candidates}
        for manifest, manifest_path in _cooling_effort_candidates(
            live_dir, now, effort_budget,
        ):
            if manifest_path not in seen_paths:
                candidates.append((manifest, manifest_path))
    candidates.sort(key=lambda pair: datetime.fromisoformat(pair[0].created_at))
    return candidates


def _cooling_effort_candidates(
    live_dir: Path,
    now: datetime,
    budget: EffortBudget,
) -> list[tuple[MigrationManifest, Path]]:
    candidates: list[tuple[MigrationManifest, Path]] = []
    for manifest, manifest_path in _iter_candidate_manifests(live_dir):
        if not _can_ignore_effort_cooldown(manifest, now, budget):
            continue
        candidates.append((manifest, manifest_path))
    return candidates


def _iter_candidate_manifests(
    live_dir: Path,
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
        candidates.append((load_manifest(manifest_path), manifest_path))
    return candidates


def _is_normally_eligible(manifest: MigrationManifest, now: datetime) -> bool:
    return (
        manifest.status in ("ready", "in-progress")
        and not manifest.awaiting_human_review
        and has_executable_phase(manifest)
        and eligible_now(manifest, now)
    )


def _can_ignore_effort_cooldown(
    manifest: MigrationManifest,
    now: datetime,
    budget: EffortBudget,
) -> bool:
    if not _is_phase_candidate(manifest):
        return False
    if manifest.cooldown_until is None:
        return False
    if datetime.fromisoformat(manifest.cooldown_until) <= now:
        return False
    phase = resolve_current_phase(manifest)
    return (
        phase.required_effort is not None
        and not effort_exceeds(phase.required_effort, budget.max_allowed_effort)
    )


def _is_phase_candidate(manifest: MigrationManifest) -> bool:
    return (
        manifest.status in ("ready", "in-progress")
        and not manifest.awaiting_human_review
        and has_executable_phase(manifest)
    )


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
    effort_budget: EffortBudget | None = None,
) -> tuple[RouteOutcome, DecisionRecord | None]:
    resolved_budget = effort_budget or resolve_effort_budget(effort, None)
    now = datetime.now(timezone.utc)
    candidates = enumerate_eligible_manifests(live_dir, now, resolved_budget)
    deferred_record: DecisionRecord | None = None
    pending_defers: list[tuple[MigrationManifest, Path]] = []

    for manifest, manifest_path in candidates:
        phase = resolve_current_phase(manifest)
        target_label = _target_label(manifest, phase)
        if (
            phase.required_effort is not None
            and effort_exceeds(
                phase.required_effort,
                resolved_budget.max_allowed_effort,
            )
        ):
            reason = _effort_defer_reason(
                phase,
                max_allowed_effort=resolved_budget.max_allowed_effort,
            )
            _log_phase_effort_deferred(
                artifacts,
                target_label,
                phase,
                reason,
                max_allowed_effort=resolved_budget.max_allowed_effort,
            )
            pending_defers.append(
                (
                    _defer_manifest(
                        manifest,
                        now,
                        verdict="effort-over-budget",
                        reason=reason,
                    ),
                    manifest_path,
                )
            )
            deferred_record = _effort_deferred_record(reason, repo_root, target_label)
            continue

        phase_resolution = resolve_phase_effort(
            resolved_budget,
            phase.required_effort,
            reason=phase.effort_reason,
        )
        phase_effort = phase_resolution.effective_effort
        effort_metadata = phase_resolution.event_fields()
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
                effort=phase_effort,
                effort_metadata=effort_metadata,
                timeout=timeout,
            )
        except ContinuousRefactorError as error:
            return "abandon", _ready_check_failure_record(error, repo_root, target_label)

        verdict, reason = _normalize_ready_verdict(verdict, reason)

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
                effort=phase_effort,
                effort_metadata=effort_metadata,
                timeout=timeout,
                validation_command=validation_command,
                max_attempts=max_attempts,
            )

            if outcome.status != "failed":
                finalize_commit(
                    repo_root,
                    head_before,
                    build_commit_message(
                        f"{commit_message_prefix}: migration/{manifest.name}"
                        f"/{phase_file_reference(phase)}",
                        why=sanitized_text_or(outcome.reason, repo_root, outcome.reason),
                        validation=validation_command,
                    ),
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
            return "commit", _phase_commit_record(outcome, repo_root, target_label)

        pending_defers.append(
            (
                _defer_manifest(manifest, now, verdict=verdict, reason=reason),
                manifest_path,
            )
        )
        if verdict == "unverifiable":
            _save_pending_defers(pending_defers)
            return "blocked", _human_review_record(reason, repo_root, target_label)
        deferred_record = _deferred_record(reason, repo_root, target_label)

    _save_pending_defers(pending_defers)
    return "not-routed", deferred_record


def _target_label(manifest: MigrationManifest, phase: PhaseSpec) -> str:
    return f"{manifest.name} {phase_file_reference(phase)} ({phase.name})"


def _normalize_ready_verdict(
    verdict: ReadyVerdict,
    reason: str,
) -> tuple[ReadyVerdict, str]:
    if verdict != "unverifiable":
        return verdict, reason
    if not _is_baseline_validation_uncertainty(reason):
        return verdict, reason
    return "no", reason


def _is_baseline_validation_uncertainty(reason: str) -> bool:
    reason_lower = reason.lower()
    return any(
        phrase in reason_lower
        for phrase in _BASELINE_VALIDATION_UNCERTAINTY_PHRASES
    )


def _save_pending_defers(
    pending_defers: list[tuple[MigrationManifest, Path]],
) -> None:
    for deferred_manifest, manifest_path in pending_defers:
        save_manifest(deferred_manifest, manifest_path)


def _effort_defer_reason(
    phase: PhaseSpec,
    *,
    max_allowed_effort: str,
) -> str:
    detail = (
        f" Reason: {phase.effort_reason}."
        if phase.effort_reason
        else ""
    )
    return (
        f"Phase requires {phase.required_effort} effort, above this run's "
        f"max allowed effort {max_allowed_effort}.{detail}"
    )


def _log_phase_effort_deferred(
    artifacts: RunArtifacts,
    target_label: str,
    phase: PhaseSpec,
    reason: str,
    *,
    max_allowed_effort: str,
) -> None:
    artifacts.log(
        "INFO",
        f"phase effort deferred: {target_label}",
        event="phase_effort_deferred",
        target=target_label,
        required_effort=phase.required_effort,
        max_allowed_effort=max_allowed_effort,
        effort_reason=phase.effort_reason,
        summary=reason,
    )


def _ready_check_failure_record(
    error: ContinuousRefactorError, repo_root: Path, target_label: str,
) -> DecisionRecord:
    summary = sanitized_text_or(str(error), repo_root, str(error))
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
        summary=sanitized_text_or(outcome.reason, repo_root, outcome.reason),
        retry_used=outcome.retry,
    )


def _phase_commit_record(
    outcome: ExecutePhaseOutcome,
    repo_root: Path,
    target_label: str,
) -> DecisionRecord:
    return DecisionRecord(
        decision="commit",
        retry_recommendation="none",
        target=target_label,
        call_role="phase.execute",
        phase_reached="phase.execute",
        failure_kind="none",
        summary=sanitized_text_or(outcome.reason, repo_root, outcome.reason),
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
    summary = sanitized_text_or(reason, repo_root, "Phase requires human review")
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
        summary=sanitized_text_or(reason, repo_root, "Migration phase not ready"),
    )


def _effort_deferred_record(
    reason: str, repo_root: Path, target_label: str,
) -> DecisionRecord:
    return DecisionRecord(
        decision="retry",
        retry_recommendation="same-target",
        target=target_label,
        call_role="phase.effort-budget",
        phase_reached="phase.effort-budget",
        failure_kind="phase-effort-over-budget",
        summary=sanitized_text_or(
            reason,
            repo_root,
            "Migration phase over effort budget",
        ),
    )
