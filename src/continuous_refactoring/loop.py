from __future__ import annotations

import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

    from continuous_refactoring.artifacts import RunArtifacts
    from continuous_refactoring.migrations import MigrationManifest

__all__ = [
    "run_baseline_checks",
    "run_loop",
    "run_migrations_focused_loop",
    "run_once",
]

from continuous_refactoring.artifacts import (
    ContinuousRefactorError,
    create_run_artifacts,
)
from continuous_refactoring.agent import (
    maybe_run_agent,
    run_tests,
    summarize_output,
)
from continuous_refactoring.config import (
    load_taste,
    resolve_live_migrations_dir,
    resolve_project,
)
from continuous_refactoring.decisions import (
    DecisionRecord,
    default_retry_recommendation,
    error_failure_kind,
    read_status,
    resolved_phase_reached,
    sanitize_text,
    status_summary,
)
from continuous_refactoring.failure_report import effective_record, persist_decision
from continuous_refactoring.git import (
    discard_workspace_changes,
    get_head_sha,
    git_commit,
    repo_change_count,
    require_clean_worktree,
    revert_to,
    run_command,
)
from continuous_refactoring.prompts import (
    DEFAULT_FIX_AMENDMENT,
    DEFAULT_REFACTORING_PROMPT,
    compose_full_prompt,
    prompt_file_text,
)
import continuous_refactoring.routing_pipeline as routing_pipeline
from continuous_refactoring.targeting import Target, resolve_targets


def run_baseline_checks(
    test_command: str,
    repo_root: Path,
    *,
    stdout_path: Path,
    stderr_path: Path,
) -> tuple[bool, str]:
    result = run_tests(
        test_command,
        repo_root,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
    if result.returncode == 0:
        return True, ""
    return False, summarize_output(result)


def _load_taste_safe(repo_root: Path) -> str:
    try:
        project = resolve_project(repo_root)
        return load_taste(project)
    except ContinuousRefactorError:
        return load_taste(None)


def _resolve_live_migrations_dir(repo_root: Path) -> Path | None:
    try:
        project = resolve_project(repo_root)
    except ContinuousRefactorError:
        return None
    return resolve_live_migrations_dir(project)


def _retry_context(record: DecisionRecord) -> str:
    lines = [
        f"- Previous attempt on `{record.target}` failed during `{record.call_role}`.",
        f"- Summary: {record.summary}",
    ]
    if record.next_retry_focus:
        lines.append(f"- Next retry focus: {record.next_retry_focus}")
    return "\n".join(lines)

def _run_refactor_attempt(
    *,
    repo_root: Path,
    artifacts: RunArtifacts,
    target: Target,
    attempt: int,
    retry: int,
    agent: str,
    model: str,
    effort: str,
    prompt: str,
    timeout: int | None,
    validation_command: str,
    show_agent_logs: bool,
    show_command_logs: bool,
    commit_message_prefix: str,
) -> DecisionRecord:
    discard_workspace_changes(repo_root)
    head_before = get_head_sha(repo_root)

    if retry > 1:
        print(f"  retry {retry}")

    attempt_dir = artifacts.attempt_dir(attempt, retry=retry) / "refactor"
    last_message_path = (
        attempt_dir / "agent-last-message.md" if agent == "codex" else None
    )
    agent_stdout = attempt_dir / "agent.stdout.log"
    agent_stderr = attempt_dir / "agent.stderr.log"
    tests_stdout = attempt_dir / "tests.stdout.log"
    tests_stderr = attempt_dir / "tests.stderr.log"
    call_role = "refactor"
    phase_reached = "refactor"

    artifacts.log_call_started(
        attempt=attempt,
        retry=retry,
        target=target.description,
        call_role=call_role,
    )
    try:
        agent_result = maybe_run_agent(
            agent=agent,
            model=model,
            effort=effort,
            prompt=prompt,
            repo_root=repo_root,
            stdout_path=agent_stdout,
            stderr_path=agent_stderr,
            last_message_path=last_message_path,
            mirror_to_terminal=show_agent_logs,
            timeout=timeout,
        )
    except ContinuousRefactorError as error:
        artifacts.log_call_finished(
            attempt=attempt,
            retry=retry,
            target=target.description,
            call_role=call_role,
            status="failed",
            level="WARN",
            summary=str(error),
        )
        revert_to(repo_root, head_before)
        agent_status = read_status(
            agent,
            last_message_path=last_message_path,
            fallback_text=None,
        )
        summary, focus = status_summary(
            agent_status,
            fallback=sanitize_text(str(error), repo_root) or str(error),
            repo_root=repo_root,
        )
        return DecisionRecord(
            decision="retry",
            retry_recommendation="same-target",
            target=target.description,
            call_role=call_role,
            phase_reached=resolved_phase_reached(agent_status, phase_reached),
            failure_kind=error_failure_kind(str(error)),
            summary=summary,
            next_retry_focus=focus,
            agent_last_message_path=last_message_path,
            agent_stdout_path=agent_stdout,
            agent_stderr_path=agent_stderr,
        )

    agent_status = read_status(
        agent,
        last_message_path=last_message_path,
        fallback_text=agent_result.stdout,
    )
    if agent_result.returncode != 0:
        summary, focus = status_summary(
            agent_status,
            fallback=f"{agent} exited with code {agent_result.returncode}",
            repo_root=repo_root,
        )
        artifacts.log_call_finished(
            attempt=attempt,
            retry=retry,
            target=target.description,
            call_role=call_role,
            status="failed",
            level="WARN",
            returncode=agent_result.returncode,
            summary=summary,
        )
        revert_to(repo_root, head_before)
        return DecisionRecord(
            decision="retry",
            retry_recommendation="same-target",
            target=target.description,
            call_role=call_role,
            phase_reached=resolved_phase_reached(agent_status, phase_reached),
            failure_kind="agent-exited-nonzero",
            summary=summary,
            next_retry_focus=focus,
            agent_last_message_path=last_message_path,
            agent_stdout_path=agent_result.stdout_path,
            agent_stderr_path=agent_result.stderr_path,
        )

    artifacts.log_call_finished(
        attempt=attempt,
        retry=retry,
        target=target.description,
        call_role=call_role,
        status="finished",
        returncode=agent_result.returncode,
    )

    validation_role = "validation"
    artifacts.log_call_started(
        attempt=attempt,
        retry=retry,
        target=target.description,
        call_role=validation_role,
        phase_reached=resolved_phase_reached(agent_status, phase_reached),
    )
    try:
        validation_result = run_tests(
            validation_command,
            repo_root,
            stdout_path=tests_stdout,
            stderr_path=tests_stderr,
            mirror_to_terminal=show_command_logs,
        )
    except ContinuousRefactorError as error:
        artifacts.log_call_finished(
            attempt=attempt,
            retry=retry,
            target=target.description,
            call_role=validation_role,
            phase_reached=resolved_phase_reached(agent_status, phase_reached),
            status="failed",
            level="WARN",
            summary=str(error),
        )
        revert_to(repo_root, head_before)
        summary, focus = status_summary(
            agent_status,
            fallback=sanitize_text(str(error), repo_root) or str(error),
            repo_root=repo_root,
        )
        return DecisionRecord(
            decision="retry",
            retry_recommendation="same-target",
            target=target.description,
            call_role=validation_role,
            phase_reached=resolved_phase_reached(agent_status, phase_reached),
            failure_kind="validation-infra-failure",
            summary=summary,
            next_retry_focus=focus,
            agent_last_message_path=last_message_path,
            agent_stdout_path=agent_result.stdout_path,
            agent_stderr_path=agent_result.stderr_path,
            tests_stdout_path=tests_stdout,
            tests_stderr_path=tests_stderr,
        )

    if validation_result.returncode != 0:
        summary, focus = status_summary(
            agent_status,
            fallback="validation failed after refactor",
            repo_root=repo_root,
        )
        artifacts.log_call_finished(
            attempt=attempt,
            retry=retry,
            target=target.description,
            call_role=validation_role,
            phase_reached=resolved_phase_reached(agent_status, phase_reached),
            status="failed",
            level="WARN",
            returncode=validation_result.returncode,
            summary=summary,
        )
        revert_to(repo_root, head_before)
        return DecisionRecord(
            decision="retry",
            retry_recommendation="same-target",
            target=target.description,
            call_role=validation_role,
            phase_reached=resolved_phase_reached(agent_status, phase_reached),
            failure_kind="validation-failed",
            summary=summary,
            next_retry_focus=focus,
            agent_last_message_path=last_message_path,
            agent_stdout_path=agent_result.stdout_path,
            agent_stderr_path=agent_result.stderr_path,
            tests_stdout_path=validation_result.stdout_path,
            tests_stderr_path=validation_result.stderr_path,
        )

    artifacts.log_call_finished(
        attempt=attempt,
        retry=retry,
        target=target.description,
        call_role=validation_role,
        phase_reached=resolved_phase_reached(agent_status, phase_reached),
        status="finished",
        returncode=validation_result.returncode,
    )

    if agent_status and agent_status.decision in {"retry", "abandon", "blocked"}:
        revert_to(repo_root, head_before)
        summary, focus = status_summary(
            agent_status,
            fallback=f"agent requested {agent_status.decision}",
            repo_root=repo_root,
        )
        decision = agent_status.decision
        retry_recommendation = (
            agent_status.retry_recommendation
            or default_retry_recommendation(decision)
        )
        return DecisionRecord(
            decision=decision,
            retry_recommendation=retry_recommendation,
            target=target.description,
            call_role=call_role,
            phase_reached=agent_status.phase_reached or phase_reached,
            failure_kind=agent_status.failure_kind or "agent-requested-transition",
            summary=summary,
            next_retry_focus=focus,
            agent_last_message_path=last_message_path,
            agent_stdout_path=agent_result.stdout_path,
            agent_stderr_path=agent_result.stderr_path,
            tests_stdout_path=validation_result.stdout_path,
            tests_stderr_path=validation_result.stderr_path,
        )

    commit = _finalize_commit(
        repo_root,
        head_before,
        f"{commit_message_prefix}: {target.description}",
        artifacts=artifacts,
        attempt=attempt,
        phase="refactor",
    )

    return DecisionRecord(
        decision="commit",
        retry_recommendation="none",
        target=target.description,
        call_role=validation_role,
        phase_reached=resolved_phase_reached(agent_status, phase_reached),
        failure_kind="none",
        summary="Validated refactor ready to commit",
        agent_last_message_path=last_message_path,
        agent_stdout_path=agent_result.stdout_path,
        agent_stderr_path=agent_result.stderr_path,
        tests_stdout_path=validation_result.stdout_path,
        tests_stderr_path=validation_result.stderr_path,
    )


def _resolve_base_prompt(args: argparse.Namespace) -> str:
    if args.refactoring_prompt:
        return prompt_file_text(args.refactoring_prompt)
    return DEFAULT_REFACTORING_PROMPT


def _build_target_fallback(scope_instruction: str | None) -> Target:
    return Target(
        description="general refactoring",
        files=(),
        scoping=scope_instruction,
        model_override=None,
        effort_override=None,
        provenance="fallback",
    )


def _effective_max_attempts(raw: int | None) -> int | None:
    """Normalize --max-attempts: None -> 1, 0 -> None (unlimited), N -> N."""
    if raw is None:
        return 1
    if raw == 0:
        return None
    return raw


def _resolve_fix_amendment_text(args: argparse.Namespace) -> str:
    if args.fix_prompt:
        return prompt_file_text(args.fix_prompt)
    return DEFAULT_FIX_AMENDMENT


def _parse_paths_arg(raw_paths: str | None) -> tuple[str, ...] | None:
    if not raw_paths:
        return None
    parsed = tuple(path.strip() for path in raw_paths.split(":") if path.strip())
    return parsed or None


def _resolve_targets_from_args(
    args: argparse.Namespace,
    repo_root: Path,
) -> list[Target]:
    return resolve_targets(
        extensions=args.extensions,
        globs=args.globs,
        targets_path=args.targets,
        paths=_parse_paths_arg(args.paths),
        repo_root=repo_root,
    )


def _sleep_between_targets(
    sleep_seconds: float,
    *,
    artifacts: RunArtifacts,
    target_index: int,
    total_targets: int,
) -> None:
    if sleep_seconds <= 0 or target_index >= total_targets:
        return
    artifacts.log(
        "INFO",
        f"Sleeping {sleep_seconds:g}s before next target",
        event="sleep_between_targets",
        attempt=target_index,
        sleep_seconds=sleep_seconds,
    )
    print(f"Sleeping {sleep_seconds:g}s before next target")
    time.sleep(sleep_seconds)


def _finalize_commit(
    repo_root: Path,
    head_before: str,
    commit_message: str,
    *,
    artifacts: RunArtifacts,
    attempt: int,
    phase: str,
) -> str | None:
    head_after = get_head_sha(repo_root)
    if head_after == head_before and repo_change_count(repo_root) == 0:
        return None

    # The runner owns the final commit. If an agent already committed, squash it
    # back into a single driver commit so logs and artifacts match git history.
    if head_after != head_before:
        run_command(["git", "reset", "--soft", head_before], cwd=repo_root)

    commit = git_commit(repo_root, commit_message)
    artifacts.record_commit(attempt, phase, commit)
    print(f"Committed: {commit}")
    return commit


def run_once(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    timeout = args.timeout or 900
    max_attempts_effective = _effective_max_attempts(
        getattr(args, "max_attempts", None)
    )
    taste = _load_taste_safe(repo_root)

    targets = _resolve_targets_from_args(args, repo_root)
    target = (
        random.choice(targets)
        if targets
        else _build_target_fallback(args.scope_instruction)
    )

    base_prompt = _resolve_base_prompt(args)
    model = target.model_override or args.model
    effort = target.effort_override or args.effort

    artifacts = create_run_artifacts(
        repo_root,
        agent=args.agent,
        model=model,
        effort=effort,
        test_command=args.validation_command,
    )
    artifacts.log("INFO", f"run artifacts: {artifacts.root}", event="artifacts_ready")

    final_status = "running"
    error_message: str | None = None
    try:
        require_clean_worktree(repo_root)

        artifacts.mark_attempt_started(1)

        print(f"\n── Target: {target.description} ──")
        route_result = routing_pipeline.route_and_run(
            target, taste, repo_root, artifacts,
            live_dir=_resolve_live_migrations_dir(repo_root),
            agent=args.agent, model=model, effort=effort,
            timeout=timeout,
            commit_message_prefix="continuous refactor",
            validation_command=args.validation_command,
            max_attempts=max_attempts_effective,
            attempt=1,
            finalize_commit=_finalize_commit,
        )
        target = route_result.target
        if route_result.outcome == "commit":
            final_status = "completed"
            return 0
        if route_result.outcome in {"abandon", "blocked"}:
            final_status = "migration_failed"
            raise ContinuousRefactorError(
                route_result.decision_record.summary
                if route_result.decision_record is not None
                else "Migration phase execution failed"
            )

        prompt = compose_full_prompt(
            base_prompt=base_prompt,
            taste=taste,
            target=target,
            scope_instruction=args.scope_instruction,
            validation_command=args.validation_command,
            attempt=1,
        )

        head_before = get_head_sha(repo_root)

        attempt_dir = artifacts.attempt_dir(1) / "refactor"
        last_message_path = (
            attempt_dir / "agent-last-message.md" if args.agent == "codex" else None
        )

        agent_result = maybe_run_agent(
            agent=args.agent,
            model=model,
            effort=effort,
            prompt=prompt,
            repo_root=repo_root,
            stdout_path=attempt_dir / "agent.stdout.log",
            stderr_path=attempt_dir / "agent.stderr.log",
            last_message_path=last_message_path,
            mirror_to_terminal=args.show_agent_logs,
            timeout=timeout,
        )

        if agent_result.returncode != 0:
            final_status = "agent_failed"
            raise ContinuousRefactorError(
                f"Agent failed with exit code {agent_result.returncode}"
            )

        validation_result = run_tests(
            args.validation_command,
            repo_root,
            stdout_path=attempt_dir / "tests.stdout.log",
            stderr_path=attempt_dir / "tests.stderr.log",
            mirror_to_terminal=args.show_command_logs,
        )

        if validation_result.returncode != 0:
            revert_to(repo_root, head_before)
            final_status = "validation_failed"
            raise ContinuousRefactorError("Validation failed after agent run")

        _finalize_commit(
            repo_root,
            head_before,
            "continuous refactor: run-once",
            artifacts=artifacts,
            attempt=1,
            phase="run_once",
        )

        diff_stat = run_command(
            ["git", "show", "--stat", "HEAD"],
            cwd=repo_root,
            check=False,
        )
        print(diff_stat.stdout)
        final_status = "completed"
        return 0

    except ContinuousRefactorError as error:
        if final_status == "running":
            final_status = "failed"
        error_message = str(error)
        raise
    except KeyboardInterrupt:
        final_status = "interrupted"
        artifacts.log("WARN", "Interrupted", event="interrupted")
        print(f"\nArtifact logs: {artifacts.root}", file=sys.stderr)
        return 130
    finally:
        artifacts.finish(final_status, error_message=error_message)


def run_loop(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    timeout = args.timeout or 1800
    sleep_seconds = getattr(args, "sleep", 0.0)
    max_consecutive = args.max_consecutive_failures
    max_attempts_effective = _effective_max_attempts(
        getattr(args, "max_attempts", None)
    )
    taste = _load_taste_safe(repo_root)

    targets = _resolve_targets_from_args(args, repo_root)
    random.shuffle(targets)

    max_refactors = args.max_refactors
    if max_refactors is None and args.targets:
        max_refactors = len(targets)
    if max_refactors and len(targets) > max_refactors:
        targets = targets[:max_refactors]

    fell_back_to_scope = False
    if not targets:
        targets = [_build_target_fallback(args.scope_instruction)]
        fell_back_to_scope = bool(args.extensions or args.globs or args.paths)

    base_prompt = _resolve_base_prompt(args)
    fix_amendment_text = _resolve_fix_amendment_text(args)

    artifacts = create_run_artifacts(
        repo_root,
        agent=args.agent,
        model=args.model,
        effort=args.effort,
        test_command=args.validation_command,
    )
    artifacts.log("INFO", f"run artifacts: {artifacts.root}", event="artifacts_ready")
    if max_attempts_effective is None:
        artifacts.log(
            "WARN",
            "max_attempts=0: unlimited retries; permanently-broken targets will not exit",
            event="max_attempts_unlimited",
        )
    if fell_back_to_scope:
        artifacts.log(
            "INFO",
            "Targeting patterns matched no tracked files; falling back to scope-instruction.",
            event="targeting_fallback",
        )

    final_status = "running"
    error_message: str | None = None
    consecutive_failures = 0
    total_targets = len(targets)

    try:
        require_clean_worktree(repo_root)

        baseline_ok, baseline_context = run_baseline_checks(
            args.validation_command,
            repo_root,
            stdout_path=artifacts.baseline_dir("initial") / "tests.stdout.log",
            stderr_path=artifacts.baseline_dir("initial") / "tests.stderr.log",
        )
        if not baseline_ok:
            final_status = "baseline_failed"
            raise ContinuousRefactorError(
                f"Baseline validation failed\n{baseline_context}"
            )

        for target_index, target in enumerate(targets, start=1):
            artifacts.mark_attempt_started(target_index)

            model = target.model_override or args.model
            effort = target.effort_override or args.effort

            print(
                f"\n── Target {target_index}/{total_targets}: {target.description} ──"
            )
            route_result = routing_pipeline.route_and_run(
                target, taste, repo_root, artifacts,
                live_dir=_resolve_live_migrations_dir(repo_root),
                agent=args.agent, model=model, effort=effort,
                timeout=timeout,
                commit_message_prefix=args.commit_message_prefix,
                validation_command=args.validation_command,
                max_attempts=max_attempts_effective,
                attempt=target_index,
                finalize_commit=_finalize_commit,
            )
            target = route_result.target
            if route_result.outcome == "commit":
                if route_result.decision_record is not None:
                    persist_decision(
                        repo_root,
                        artifacts,
                        attempt=target_index,
                        retry=route_result.decision_record.retry_used,
                        validation_command=args.validation_command,
                        record=route_result.decision_record,
                    )
                consecutive_failures = 0
                _sleep_between_targets(
                    sleep_seconds,
                    artifacts=artifacts,
                    target_index=target_index,
                    total_targets=total_targets,
                )
                continue
            if route_result.outcome in {"abandon", "blocked"}:
                if route_result.decision_record is not None:
                    persist_decision(
                        repo_root,
                        artifacts,
                        attempt=target_index,
                        retry=route_result.decision_record.retry_used,
                        validation_command=args.validation_command,
                        record=route_result.decision_record,
                    )
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive:
                    final_status = "max_consecutive_failures"
                    raise ContinuousRefactorError(
                        f"Stopping: {max_consecutive} consecutive failures"
                    )
                _sleep_between_targets(
                    sleep_seconds,
                    artifacts=artifacts,
                    target_index=target_index,
                    total_targets=total_targets,
                )
                continue

            retry_context: str | None = None
            outcome_record: DecisionRecord | None = None
            retry = 0

            while True:
                retry += 1
                prompt = compose_full_prompt(
                    base_prompt=base_prompt,
                    taste=taste,
                    target=target,
                    scope_instruction=args.scope_instruction,
                    validation_command=args.validation_command,
                    attempt=retry,
                    retry_context=retry_context,
                    fix_amendment=fix_amendment_text if retry > 1 else None,
                )
                record = _run_refactor_attempt(
                    repo_root=repo_root,
                    artifacts=artifacts,
                    target=target,
                    attempt=target_index,
                    retry=retry,
                    agent=args.agent,
                    model=model,
                    effort=effort,
                    prompt=prompt,
                    timeout=timeout,
                    validation_command=args.validation_command,
                    show_agent_logs=args.show_agent_logs,
                    show_command_logs=args.show_command_logs,
                    commit_message_prefix=args.commit_message_prefix,
                )
                record_to_persist = effective_record(
                    record,
                    retry=retry,
                    max_attempts=max_attempts_effective,
                )
                if (
                    record.decision == "retry"
                    and record_to_persist.decision == "abandon"
                    and max_attempts_effective is not None
                ):
                    artifacts.log(
                        "WARN",
                        f"Exhausted {max_attempts_effective} attempts: {target.description}",
                        event="max_attempts_exhausted",
                        attempt=target_index,
                        retry=retry,
                        target=target.description,
                        call_role=record.call_role,
                    )
                persist_decision(
                    repo_root,
                    artifacts,
                    attempt=target_index,
                    retry=retry,
                    validation_command=args.validation_command,
                    record=record_to_persist,
                )
                outcome_record = record_to_persist
                if record_to_persist.decision == "retry":
                    retry_context = _retry_context(record_to_persist)
                    continue
                break

            if outcome_record is not None and outcome_record.decision == "commit":
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive:
                    final_status = "max_consecutive_failures"
                    raise ContinuousRefactorError(
                        f"Stopping: {max_consecutive} consecutive failures"
                    )

            _sleep_between_targets(
                sleep_seconds,
                artifacts=artifacts,
                target_index=target_index,
                total_targets=total_targets,
            )

        final_status = "completed"
        return 0

    except ContinuousRefactorError as error:
        if final_status == "running":
            final_status = "failed"
        error_message = str(error)
        raise
    except KeyboardInterrupt:
        final_status = "interrupted"
        artifacts.log("WARN", "Interrupted", event="interrupted")
        discard_workspace_changes(repo_root)
        print(f"\nArtifact logs: {artifacts.root}", file=sys.stderr)
        return 130
    finally:
        artifacts.finish(final_status, error_message=error_message)


def _focus_eligible_manifests(
    live_dir: Path, now: datetime,
) -> list[tuple[MigrationManifest, Path]]:
    return [
        pair for pair in routing_pipeline.enumerate_eligible_manifests(live_dir, now)
        if not pair[0].awaiting_human_review
    ]


def run_migrations_focused_loop(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    timeout = args.timeout or 1800
    sleep_seconds = getattr(args, "sleep", 0.0)
    max_consecutive = args.max_consecutive_failures
    max_attempts_effective = _effective_max_attempts(
        getattr(args, "max_attempts", None)
    )
    taste = _load_taste_safe(repo_root)

    live_dir = _resolve_live_migrations_dir(repo_root)
    if live_dir is None:
        raise ContinuousRefactorError(
            "no live-migrations-dir configured for this project; "
            "run `continuous-refactoring init --live-migrations-dir <dir>` first."
        )

    artifacts = create_run_artifacts(
        repo_root,
        agent=args.agent,
        model=args.model,
        effort=args.effort,
        test_command=args.validation_command,
    )
    artifacts.log("INFO", f"run artifacts: {artifacts.root}", event="artifacts_ready")
    artifacts.log(
        "INFO",
        f"focus-on-live-migrations: {live_dir}",
        event="focus_on_live_migrations",
    )
    if max_attempts_effective is None:
        artifacts.log(
            "WARN",
            "max_attempts=0: unlimited retries; permanently-broken targets will not exit",
            event="max_attempts_unlimited",
        )

    final_status = "running"
    error_message: str | None = None
    consecutive_failures = 0
    iteration = 0

    try:
        require_clean_worktree(repo_root)

        baseline_ok, baseline_context = run_baseline_checks(
            args.validation_command,
            repo_root,
            stdout_path=artifacts.baseline_dir("initial") / "tests.stdout.log",
            stderr_path=artifacts.baseline_dir("initial") / "tests.stderr.log",
        )
        if not baseline_ok:
            final_status = "baseline_failed"
            raise ContinuousRefactorError(
                f"Baseline validation failed\n{baseline_context}"
            )

        while True:
            now = datetime.now(timezone.utc)
            eligible = _focus_eligible_manifests(live_dir, now)
            if not eligible:
                print("Focused migrations loop: nothing eligible — every migration is done or blocked.")
                artifacts.log(
                    "INFO",
                    "No eligible migrations remain; terminating.",
                    event="focus_eligible_empty",
                )
                final_status = "completed"
                return 0

            iteration += 1
            artifacts.mark_attempt_started(iteration)
            names = ", ".join(m.name for m, _ in eligible)
            print(f"\n── Migration tick {iteration} (eligible: {names}) ──")

            outcome, record = routing_pipeline.try_migration_tick(
                live_dir, taste, repo_root, artifacts,
                agent=args.agent,
                model=args.model,
                effort=args.effort,
                timeout=timeout,
                commit_message_prefix=args.commit_message_prefix,
                validation_command=args.validation_command,
                max_attempts=max_attempts_effective,
                attempt=iteration,
                finalize_commit=_finalize_commit,
            )

            if record is not None:
                persist_decision(
                    repo_root,
                    artifacts,
                    attempt=iteration,
                    retry=record.retry_used,
                    validation_command=args.validation_command,
                    record=record,
                )

            if outcome == "commit":
                consecutive_failures = 0
            elif outcome in {"abandon", "blocked"}:
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive:
                    final_status = "max_consecutive_failures"
                    raise ContinuousRefactorError(
                        f"Stopping: {max_consecutive} consecutive failures"
                    )
            else:
                message = (
                    "Migration tick deferred all eligible migrations; "
                    "terminating until a wake-up window or manifest change."
                )
                if record is not None:
                    message = (
                        "Migration tick deferred all eligible migrations: "
                        f"{record.summary}"
                    )
                artifacts.log(
                    "INFO",
                    message,
                    event="focus_tick_deferred",
                )
                print(message)
                final_status = "completed"
                return 0

            if sleep_seconds > 0:
                artifacts.log(
                    "INFO",
                    f"Sleeping {sleep_seconds:g}s before next tick",
                    event="sleep_between_ticks",
                    attempt=iteration,
                    sleep_seconds=sleep_seconds,
                )
                print(f"Sleeping {sleep_seconds:g}s before next tick")
                time.sleep(sleep_seconds)

    except ContinuousRefactorError as error:
        if final_status == "running":
            final_status = "failed"
        error_message = str(error)
        raise
    except KeyboardInterrupt:
        final_status = "interrupted"
        artifacts.log("WARN", "Interrupted", event="interrupted")
        discard_workspace_changes(repo_root)
        print(f"\nArtifact logs: {artifacts.root}", file=sys.stderr)
        return 130
    finally:
        artifacts.finish(final_status, error_message=error_message)
