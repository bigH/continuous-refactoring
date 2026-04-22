"""Routing pipeline orchestration."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from continuous_refactoring.artifacts import RunArtifacts
    from continuous_refactoring.migrations import MigrationManifest

__all__ = [
    "RouteResult",
    "describe_planning_outcome",
    "enumerate_eligible_manifests",
    "expand_target_for_classification",
    "migration_name_from_target",
    "route_and_run",
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
from continuous_refactoring.planning import run_planning
from continuous_refactoring.routing import classify_target
from continuous_refactoring.scope_expansion import (
    build_scope_candidates,
    describe_scope_candidate,
    scope_candidate_to_target,
    scope_expansion_bypass_reason,
    select_scope_candidate,
    write_scope_expansion_artifacts,
)
from continuous_refactoring.targeting import Target


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


def migration_name_from_target(target: Target) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", target.description.lower()).strip("-")
    ts = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")
    prefix = slug[:40] if slug else "migration"
    return f"{prefix}-{ts}"


@dataclass(frozen=True)
class RouteResult:
    outcome: RouteOutcome
    target: Target
    planning_context: str = ""
    decision_record: DecisionRecord | None = None


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
        target_label = (
            f"{manifest.name} {phase_file_reference(phase)} ({phase.name})"
        )
        try:
            verdict, reason = check_phase_ready(
                phase,
                manifest,
                repo_root,
                artifacts,
                attempt=attempt,
                retry=1,
                agent=agent,
                model=model,
                effort=effort,
                timeout=timeout,
            )
        except ContinuousRefactorError as error:
            summary = sanitize_text(str(error), repo_root) or str(error)
            return (
                "abandon",
                DecisionRecord(
                    decision="abandon",
                    retry_recommendation="new-target",
                    target=target_label,
                    call_role="phase.ready-check",
                    phase_reached="phase.ready-check",
                    failure_kind=error_failure_kind(str(error)),
                    summary=summary,
                ),
            )

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
                return (
                    "abandon",
                    DecisionRecord(
                        decision="abandon",
                        retry_recommendation="new-target",
                        target=target_label,
                        call_role=outcome.call_role or "phase.execute",
                        phase_reached=outcome.phase_reached or "phase.execute",
                        failure_kind=outcome.failure_kind or "phase-failed",
                        summary=sanitize_text(outcome.reason, repo_root) or outcome.reason,
                        retry_used=outcome.retry,
                    ),
                )
            return (
                "commit",
                DecisionRecord(
                    decision="commit",
                    retry_recommendation="none",
                    target=target_label,
                    call_role="phase.execute",
                    phase_reached="phase.execute",
                    failure_kind="none",
                    summary="Migration phase completed successfully",
                ),
            )

        updated = replace(
            bump_last_touch(manifest, now),
            cooldown_until=(now + timedelta(hours=6)).isoformat(
                timespec="milliseconds"
            ),
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
        save_manifest(updated, manifest_path)
        if verdict == "unverifiable":
            summary = sanitize_text(reason, repo_root) or "Phase requires human review"
            return (
                "blocked",
                DecisionRecord(
                    decision="blocked",
                    retry_recommendation="human-review",
                    target=target_label,
                    call_role="phase.ready-check",
                    phase_reached="phase.ready-check",
                    failure_kind="phase-ready-unverifiable",
                    summary=summary,
                ),
            )
        deferred_record = DecisionRecord(
            decision="retry",
            retry_recommendation="same-target",
            target=target_label,
            call_role="phase.ready-check",
            phase_reached="phase.ready-check",
            failure_kind="phase-ready-no",
            summary=sanitize_text(reason, repo_root) or "Migration phase not ready",
        )

    return "not-routed", deferred_record


def _scope_bypass_context(target: Target, reason: str) -> str:
    lines = [
        f"Scope expansion bypassed: {reason}",
        "Files:",
        *(f"- {file_path}" for file_path in target.files),
    ]
    return "\n".join(lines)


def expand_target_for_classification(
    target: Target,
    taste: str,
    repo_root: Path,
    artifacts: RunArtifacts,
    *,
    agent: str,
    model: str,
    effort: str,
    timeout: int | None,
) -> tuple[Target, str]:
    scope_dir = artifacts.root / "scope-expansion"
    bypass_reason = scope_expansion_bypass_reason(target)
    if bypass_reason is not None:
        write_scope_expansion_artifacts(
            scope_dir,
            target,
            (),
            bypass_reason=bypass_reason,
        )
        bypass_line = f"selected-candidate: seed — {bypass_reason}\n"
        (scope_dir / "selection.stdout.log").write_text(bypass_line, encoding="utf-8")
        (scope_dir / "selection-last-message.md").write_text(
            bypass_line,
            encoding="utf-8",
        )
        return target, _scope_bypass_context(target, bypass_reason)

    candidates = build_scope_candidates(target, repo_root)
    selection = select_scope_candidate(
        target,
        candidates,
        taste,
        repo_root,
        artifacts,
        agent=agent,
        model=model,
        effort=effort,
        timeout=timeout,
    )
    write_scope_expansion_artifacts(
        scope_dir,
        target,
        candidates,
        selection=selection,
    )

    selected_candidate = next(
        candidate for candidate in candidates if candidate.kind == selection.kind
    )
    planning_context = describe_scope_candidate(selected_candidate)
    return scope_candidate_to_target(target, selected_candidate), planning_context


def route_and_run(
    target: Target,
    taste: str,
    repo_root: Path,
    artifacts: RunArtifacts,
    *,
    live_dir: Path | None,
    agent: str,
    model: str,
    effort: str,
    timeout: int | None,
    commit_message_prefix: str,
    validation_command: str,
    max_attempts: int | None,
    attempt: int,
    finalize_commit: _FinalizeCommit,
) -> RouteResult:
    if live_dir is None:
        return RouteResult(outcome="not-routed", target=target)

    migration_result, migration_record = try_migration_tick(
        live_dir, taste, repo_root, artifacts,
        agent=agent, model=model, effort=effort,
        timeout=timeout, commit_message_prefix=commit_message_prefix,
        validation_command=validation_command,
        max_attempts=max_attempts,
        attempt=attempt,
        finalize_commit=finalize_commit,
    )
    if migration_result != "not-routed":
        return RouteResult(
            outcome=migration_result,
            target=target,
            decision_record=migration_record,
        )

    target, planning_context = expand_target_for_classification(
        target,
        taste,
        repo_root,
        artifacts,
        agent=agent,
        model=model,
        effort=effort,
        timeout=timeout,
    )

    try:
        decision = classify_target(
            target,
            taste,
            repo_root,
            artifacts,
            attempt=attempt,
            retry=1,
            agent=agent,
            model=model,
            effort=effort,
            timeout=timeout,
        )
    except ContinuousRefactorError as error:
        summary = sanitize_text(str(error), repo_root) or str(error)
        return RouteResult(
            outcome="abandon",
            target=target,
            planning_context=planning_context,
            decision_record=DecisionRecord(
                decision="abandon",
                retry_recommendation="new-target",
                target=target.description,
                call_role="classify",
                phase_reached="classify",
                failure_kind=error_failure_kind(str(error)),
                summary=summary,
            ),
        )
    print(f"Classification: {decision} — {target.description}")

    if decision == "cohesive-cleanup":
        return RouteResult(
            outcome="not-routed",
            target=target,
            planning_context=planning_context,
        )

    migration_name = migration_name_from_target(target)
    head_before = get_head_sha(repo_root)
    try:
        outcome = run_planning(
            migration_name,
            target.description,
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
            extra_context=planning_context,
        )
    except ContinuousRefactorError as error:
        summary = sanitize_text(str(error), repo_root) or str(error)
        call_role = "planning.final-review"
        match = re.match(r"^(planning\.[a-z0-9-]+)\s+failed:", str(error))
        if match:
            call_role = match.group(1)
        return RouteResult(
            outcome="abandon",
            target=target,
            planning_context=planning_context,
            decision_record=DecisionRecord(
                decision="abandon",
                retry_recommendation="new-target",
                target=target.description,
                call_role=call_role,
                phase_reached=call_role,
                failure_kind=error_failure_kind(str(error)),
                summary=summary,
            ),
        )

    finalize_commit(
        repo_root,
        head_before,
        f"{commit_message_prefix}: plan {migration_name}",
        artifacts=artifacts,
        attempt=attempt,
        phase="planning",
    )

    print(f"Planning: {describe_planning_outcome(outcome.status)} — {outcome.reason}")
    if outcome.status == "skipped":
        return RouteResult(
            outcome="abandon",
            target=target,
            planning_context=planning_context,
            decision_record=DecisionRecord(
                decision="abandon",
                retry_recommendation="new-target",
                target=target.description,
                call_role="planning.final-review",
                phase_reached="planning.final-review",
                failure_kind="planning-rejected",
                summary=sanitize_text(outcome.reason, repo_root) or outcome.reason,
            ),
        )
    return RouteResult(
        outcome="commit",
        target=target,
        planning_context=planning_context,
        decision_record=DecisionRecord(
            decision="commit",
            retry_recommendation="none",
            target=target.description,
            call_role="planning.final-review",
            phase_reached="planning.final-review",
            failure_kind="none",
            summary=sanitize_text(outcome.reason, repo_root) or outcome.reason,
        ),
    )


def describe_planning_outcome(status: str) -> str:
    if status == "ready":
        return "queued for execution"
    if status == "awaiting_human_review":
        return "awaiting human review"
    return status.replace("_", " ")
