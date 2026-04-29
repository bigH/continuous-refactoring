"""Routing pipeline orchestration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from continuous_refactoring.artifacts import RunArtifacts
    from continuous_refactoring.migration_tick import _FinalizeCommit

__all__ = [
    "RouteResult",
    "describe_planning_outcome",
    "expand_target_for_classification",
    "migration_name_from_target",
    "route_and_run",
]

from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.commit_messages import build_commit_message
from continuous_refactoring.decisions import (
    DecisionRecord,
    RouteOutcome,
    error_failure_kind,
    sanitize_text,
)
from continuous_refactoring.effort import EffortBudget, resolve_effort_budget
from continuous_refactoring.git import get_head_sha
from continuous_refactoring.migration_tick import try_migration_tick as _try_migration_tick
from continuous_refactoring.planning import run_planning
from continuous_refactoring.prompts import describe_scope_candidate
from continuous_refactoring.routing import classify_target
from continuous_refactoring.scope_expansion import (
    ScopeSelection,
    scope_candidate_to_target,
    scope_expansion_bypass_reason,
    select_scope_candidate,
    write_scope_selection_logs,
    write_scope_expansion_artifacts,
)
from continuous_refactoring.scope_candidates import build_scope_candidates
from continuous_refactoring.targeting import Target


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


def _sanitized_summary(text: str, repo_root: Path) -> str:
    return sanitize_text(text, repo_root) or text


def _abandon_result(
    *,
    target: Target,
    planning_context: str,
    repo_root: Path,
    error: ContinuousRefactorError,
    call_role: str,
) -> RouteResult:
    summary = _sanitized_summary(str(error), repo_root)
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


def _planning_result(
    *,
    outcome: RouteOutcome,
    target: Target,
    planning_context: str,
    repo_root: Path,
    reason: str,
) -> RouteResult:
    summary = _sanitized_summary(reason, repo_root)
    return RouteResult(
        outcome=outcome,
        target=target,
        planning_context=planning_context,
        decision_record=DecisionRecord(
            decision=outcome,
            retry_recommendation="none" if outcome == "commit" else "new-target",
            target=target.description,
            call_role="planning.final-review",
            phase_reached="planning.final-review",
            failure_kind="none" if outcome == "commit" else "planning-rejected",
            summary=summary,
        ),
    )


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
    attempt: int = 1,
    effort_metadata: dict[str, object] | None = None,
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
        write_scope_selection_logs(
            scope_dir,
            ScopeSelection(kind="seed", reason=bypass_reason),
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
        attempt=attempt,
        effort_metadata=effort_metadata,
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
    check_migrations: bool = True,
    effort_budget: EffortBudget | None = None,
    effort_metadata: dict[str, object] | None = None,
) -> RouteResult:
    resolved_budget = effort_budget or resolve_effort_budget(effort, None)
    if live_dir is None:
        return RouteResult(outcome="not-routed", target=target)

    if check_migrations:
        migration_result, migration_record = _try_migration_tick(
            live_dir, taste, repo_root, artifacts,
            agent=agent, model=model, effort=effort,
            effort_budget=resolved_budget,
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
        attempt=attempt,
        effort_metadata=effort_metadata,
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
            effort_metadata=effort_metadata,
            timeout=timeout,
        )
    except ContinuousRefactorError as error:
        return _abandon_result(
            target=target,
            planning_context=planning_context,
            repo_root=repo_root,
            error=error,
            call_role="classify",
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
            effort_budget=resolved_budget,
            effort_metadata=effort_metadata,
            timeout=timeout,
            extra_context=planning_context,
        )
    except ContinuousRefactorError as error:
        call_role = "planning.final-review"
        match = re.match(r"^(planning\.[a-z0-9-]+)\s+failed:", str(error))
        if match:
            call_role = match.group(1)
        return _abandon_result(
            target=target,
            planning_context=planning_context,
            repo_root=repo_root,
            error=error,
            call_role=call_role,
        )

    finalize_commit(
        repo_root,
        head_before,
        build_commit_message(
            f"{commit_message_prefix}: plan {migration_name}",
            why=sanitize_text(outcome.reason, repo_root) or outcome.reason,
        ),
        artifacts=artifacts,
        attempt=attempt,
        phase="planning",
    )

    print(f"Planning: {describe_planning_outcome(outcome.status)} — {outcome.reason}")
    if outcome.status == "skipped":
        return _planning_result(
            outcome="abandon",
            target=target,
            planning_context=planning_context,
            repo_root=repo_root,
            reason=outcome.reason,
        )
    return _planning_result(
        outcome="commit",
        target=target,
        planning_context=planning_context,
        repo_root=repo_root,
        reason=outcome.reason,
    )


def describe_planning_outcome(status: str) -> str:
    if status == "ready":
        return "queued for execution"
    if status == "awaiting_human_review":
        return "awaiting human review"
    return status.replace("_", " ")
