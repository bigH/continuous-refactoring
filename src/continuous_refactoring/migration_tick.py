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
from continuous_refactoring.migration_consistency import (
    MigrationConsistencyFinding,
    check_migration_consistency,
    has_blocking_consistency_findings,
    iter_visible_migration_dirs,
)
from continuous_refactoring.phases import (
    ReadyVerdict,
    check_phase_ready,
    execute_phase,
)
from continuous_refactoring.planning import PlanningStepResult, run_next_planning_step
from continuous_refactoring.planning_state import (
    PlanningState,
    is_executable_planning_step,
    load_planning_state,
    planning_state_path,
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


def enumerate_eligible_planning_manifests(
    live_dir: Path,
    now: datetime,
) -> list[tuple[MigrationManifest, Path]]:
    candidates = [
        (manifest, manifest_path)
        for manifest, manifest_path in _iter_candidate_manifests(live_dir)
        if _is_planning_candidate(manifest, now)
    ]
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
    candidates: list[tuple[MigrationManifest, Path]] = []
    for entry in iter_visible_migration_dirs(live_dir):
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


def _is_planning_candidate(manifest: MigrationManifest, now: datetime) -> bool:
    return (
        manifest.status == "planning"
        and not manifest.awaiting_human_review
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


def _first_unloadable_visible_manifest(
    live_dir: Path,
) -> tuple[Path, list[MigrationConsistencyFinding]] | None:
    for migration_dir in iter_visible_migration_dirs(live_dir):
        if not (migration_dir / "manifest.json").exists():
            continue
        findings = check_migration_consistency(migration_dir, mode="execution-gate")
        invalid_findings = [
            finding for finding in findings
            if finding.severity == "error" and finding.code == "invalid-manifest"
        ]
        if invalid_findings:
            return migration_dir, invalid_findings
    return None


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
    preflight = _first_unloadable_visible_manifest(live_dir)
    if preflight is not None:
        migration_dir, consistency_findings = preflight
        return "abandon", _consistency_failure_record(
            consistency_findings,
            repo_root,
            migration_dir.name,
        )
    candidates = enumerate_eligible_manifests(live_dir, now, resolved_budget)
    deferred_record: DecisionRecord | None = None
    pending_defers: list[tuple[MigrationManifest, Path]] = []

    for manifest, manifest_path in candidates:
        phase = resolve_current_phase(manifest)
        target_label = _target_label(manifest, phase)
        try:
            consistency_findings = check_migration_consistency(
                manifest_path.parent, mode="execution-gate",
            )
        except ContinuousRefactorError as error:
            return "abandon", _consistency_error_record(
                str(error),
                repo_root,
                target_label,
                failure_kind=error_failure_kind(str(error)),
            )
        if has_blocking_consistency_findings(consistency_findings):
            return "abandon", _consistency_failure_record(
                consistency_findings, repo_root, target_label,
            )
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


def try_planning_tick(
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
    attempt: int,
    finalize_commit: _FinalizeCommit,
    effort_budget: EffortBudget | None = None,
    effort_metadata: dict[str, object] | None = None,
) -> tuple[RouteOutcome, DecisionRecord | None]:
    now = datetime.now(timezone.utc)
    preflight = _first_unloadable_visible_manifest(live_dir)
    if preflight is not None:
        migration_dir, consistency_findings = preflight
        return "abandon", _consistency_failure_record(
            consistency_findings,
            repo_root,
            migration_dir.name,
        )

    candidates = enumerate_eligible_planning_manifests(live_dir, now)
    for manifest, manifest_path in candidates:
        migration_dir = manifest_path.parent
        try:
            consistency_findings = check_migration_consistency(
                migration_dir,
                mode="planning-snapshot",
            )
        except ContinuousRefactorError as error:
            return "blocked", _planning_state_record(
                str(error),
                repo_root,
                migration_dir.name,
                failure_kind=error_failure_kind(str(error)),
            )
        if has_blocking_consistency_findings(consistency_findings):
            return "blocked", _planning_consistency_record(
                consistency_findings,
                repo_root,
                migration_dir.name,
            )
        state_result = _load_planning_resume_state(
            migration_dir,
            repo_root,
        )
        if isinstance(state_result, DecisionRecord):
            return "blocked", state_result
        state = state_result
        step = state.next_step
        if not is_executable_planning_step(step):
            return "blocked", _planning_state_record(
                (
                    f"Planning migration has terminal next_step {step!r} "
                    "while manifest status is still planning"
                ),
                repo_root,
                manifest.name,
                failure_kind="planning-state-invalid",
            )
        head_before = get_head_sha(repo_root)
        try:
            result = run_next_planning_step(
                manifest.name,
                state.target,
                taste,
                repo_root,
                live_dir,
                artifacts,
                attempt=attempt,
                retry=1,
                agent=agent,
                model=model,
                effort=effort,
                effort_budget=effort_budget,
                effort_metadata=effort_metadata,
                timeout=timeout,
            )
        except ContinuousRefactorError as error:
            return "abandon", _planning_error_record(
                str(error),
                repo_root,
                manifest.name,
                call_role=_planning_call_role(step),
                failure_kind=error_failure_kind(str(error)),
            )

        outcome = _planning_route_outcome(result)
        if outcome == "commit":
            finalize_commit(
                repo_root,
                head_before,
                build_commit_message(
                    (
                        f"{commit_message_prefix}: planning/"
                        f"{manifest.name}/{result.step}"
                    ),
                    why=sanitize_text(result.reason, repo_root) or result.reason,
                ),
                artifacts=artifacts,
                attempt=attempt,
                phase="planning",
            )
            print(
                "Planning: "
                f"{_describe_planning_outcome(result)} — "
                f"{manifest.name}/{result.step}: {result.reason}"
            )
            return "commit", _planning_commit_record(result, repo_root)
        if outcome == "blocked":
            return "blocked", _planning_blocked_record(result, repo_root)
        return "abandon", _planning_failed_record(result, repo_root)

    return "not-routed", None


def _planning_consistency_record(
    findings: list[MigrationConsistencyFinding],
    repo_root: Path,
    migration_name: str,
) -> DecisionRecord:
    error_findings = [finding for finding in findings if finding.severity == "error"]
    codes = ", ".join(sorted({finding.code for finding in error_findings}))
    message = (
        error_findings[0].message
        if error_findings
        else "planning snapshot consistency failed"
    )
    return _planning_state_record(
        f"Planning snapshot consistency failed ({codes}): {message}",
        repo_root,
        migration_name,
        failure_kind="planning-consistency-error",
    )


def _load_planning_resume_state(
    migration_dir: Path,
    repo_root: Path,
) -> PlanningState | DecisionRecord:
    state_path = planning_state_path(migration_dir)
    if not state_path.exists():
        return _planning_state_record(
            f"Planning migration is missing {state_path.relative_to(migration_dir)}",
            repo_root,
            migration_dir.name,
            failure_kind="planning-state-missing",
        )
    try:
        return load_planning_state(
            repo_root,
            state_path,
            published_migration_root=migration_dir,
        )
    except ContinuousRefactorError as error:
        return _planning_state_record(
            str(error),
            repo_root,
            migration_dir.name,
            failure_kind="planning-state-invalid",
        )


def _planning_route_outcome(result: PlanningStepResult) -> RouteOutcome:
    if result.status == "published":
        return "commit"
    if result.status == "blocked":
        return "blocked"
    return "abandon"


def _planning_call_role(step: object) -> str:
    if is_executable_planning_step(step):
        return f"planning.{step}"
    return "planning.resume"


def _describe_planning_outcome(result: PlanningStepResult) -> str:
    if result.terminal_outcome is None:
        return f"{result.step} accepted"
    if result.terminal_outcome.status == "ready":
        return "queued for execution"
    if result.terminal_outcome.status == "awaiting_human_review":
        return "awaiting human review"
    return result.terminal_outcome.status.replace("_", " ")


def _planning_state_record(
    message: str,
    repo_root: Path,
    migration_name: str,
    *,
    failure_kind: str,
) -> DecisionRecord:
    return DecisionRecord(
        decision="blocked",
        retry_recommendation="human-review",
        target=migration_name,
        call_role="planning.state",
        phase_reached="planning.state",
        failure_kind=failure_kind,
        summary=sanitized_text_or(message, repo_root, message),
    )


def _planning_error_record(
    message: str,
    repo_root: Path,
    migration_name: str,
    *,
    call_role: str,
    failure_kind: str,
) -> DecisionRecord:
    return DecisionRecord(
        decision="abandon",
        retry_recommendation="new-target",
        target=migration_name,
        call_role=call_role,
        phase_reached=call_role,
        failure_kind=failure_kind,
        summary=sanitized_text_or(message, repo_root, message),
    )


def _planning_commit_record(
    result: PlanningStepResult,
    repo_root: Path,
) -> DecisionRecord:
    call_role = f"planning.{result.step}"
    return DecisionRecord(
        decision="commit",
        retry_recommendation="none",
        target=result.migration_name,
        call_role=call_role,
        phase_reached=call_role,
        failure_kind="none",
        summary=sanitized_text_or(result.reason, repo_root, result.reason),
    )


def _planning_blocked_record(
    result: PlanningStepResult,
    repo_root: Path,
) -> DecisionRecord:
    return DecisionRecord(
        decision="blocked",
        retry_recommendation="human-review",
        target=result.migration_name,
        call_role="planning.publish",
        phase_reached="planning.publish",
        failure_kind="planning-publish-blocked",
        summary=sanitized_text_or(result.reason, repo_root, result.reason),
    )


def _planning_failed_record(
    result: PlanningStepResult,
    repo_root: Path,
) -> DecisionRecord:
    call_role = f"planning.{result.step}"
    return DecisionRecord(
        decision="abandon",
        retry_recommendation="new-target",
        target=result.migration_name,
        call_role=call_role,
        phase_reached=call_role,
        failure_kind="planning-step-failed",
        summary=sanitized_text_or(result.reason, repo_root, result.reason),
    )


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


def _consistency_failure_record(
    findings: list[MigrationConsistencyFinding],
    repo_root: Path,
    target_label: str,
) -> DecisionRecord:
    error_findings = [finding for finding in findings if finding.severity == "error"]
    codes = ", ".join(sorted({finding.code for finding in error_findings}))
    message = (
        error_findings[0].message
        if error_findings
        else "migration consistency failed"
    )
    summary = f"Migration consistency failed ({codes}): {message}"
    return _consistency_error_record(
        summary,
        repo_root,
        target_label,
        failure_kind="migration-consistency-error",
    )


def _consistency_error_record(
    message: str,
    repo_root: Path,
    target_label: str,
    *,
    failure_kind: str,
) -> DecisionRecord:
    return DecisionRecord(
        decision="abandon",
        retry_recommendation="new-target",
        target=target_label,
        call_role="phase.execution-gate",
        phase_reached="phase.execution-gate",
        failure_kind=failure_kind,
        summary=sanitized_text_or(message, repo_root, message),
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
