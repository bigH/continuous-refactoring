from __future__ import annotations

import random
import re
import sys
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import argparse

    from continuous_refactoring.artifacts import RunArtifacts
    from continuous_refactoring.migrations import MigrationManifest

__all__ = [
    "run_baseline_checks",
    "run_loop",
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
from continuous_refactoring.git import (
    checkout_branch,
    current_branch,
    detect_main_branch,
    discard_workspace_changes,
    generate_run_branch_name,
    generate_run_once_branch_name,
    get_head_sha,
    git_commit,
    git_push,
    prepare_phase_branch,
    prepare_run_branch,
    repo_change_count,
    require_clean_worktree,
    revert_to,
    run_command,
)
from continuous_refactoring.migrations import (
    bump_last_touch,
    eligible_now,
    has_executable_phase,
    load_manifest,
    save_manifest,
)
from continuous_refactoring.phases import (
    check_phase_ready,
    execute_phase,
    generate_phase_branch_name,
)
from continuous_refactoring.planning import run_planning
from continuous_refactoring.prompts import (
    DEFAULT_FIX_AMENDMENT,
    DEFAULT_REFACTORING_PROMPT,
    compose_full_prompt,
    prompt_file_text,
)
from continuous_refactoring.routing import classify_target
from continuous_refactoring.scope_expansion import (
    build_scope_candidates,
    describe_scope_candidate,
    scope_candidate_to_target,
    scope_expansion_bypass_reason,
    select_scope_candidate,
    write_scope_expansion_artifacts,
)
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


def _migration_name_from_target(target: Target) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", target.description.lower()).strip("-")
    ts = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")
    prefix = slug[:40] if slug else "migration"
    return f"{prefix}-{ts}"


TickOutcome = Literal["not-routed", "success", "failed"]


@dataclass(frozen=True)
class RouteResult:
    outcome: TickOutcome
    target: Target
    planning_context: str = ""


def _enumerate_eligible_manifests(
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


def _try_migration_tick(
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
) -> TickOutcome:
    now = datetime.now(timezone.utc)
    candidates = _enumerate_eligible_manifests(live_dir, now)

    for manifest, manifest_path in candidates:
        phase = manifest.phases[manifest.current_phase]
        verdict, _reason = check_phase_ready(
            phase, manifest, repo_root, artifacts,
            agent=agent, model=model, effort=effort, timeout=timeout,
        )

        if verdict == "yes":
            phase_branch = generate_phase_branch_name(
                manifest.name, manifest.current_phase, phase.name,
            )
            saved_branch = current_branch(repo_root)
            prepare_phase_branch(repo_root, phase_branch)
            head_before = get_head_sha(repo_root)

            outcome = execute_phase(
                phase, manifest, taste, repo_root, live_dir, artifacts,
                agent=agent, model=model, effort=effort, timeout=timeout,
            )

            if outcome.status != "failed":
                _finalize_commit(
                    repo_root,
                    head_before,
                    f"{commit_message_prefix}: migration/{manifest.name}"
                    f"/phase-{manifest.current_phase}/{phase.name}",
                    artifacts=artifacts,
                    attempt=attempt,
                    phase="migration",
                )

            checkout_branch(repo_root, saved_branch)

            print(
                f"Migration: {outcome.status}"
                f" — {manifest.name} phase-{manifest.current_phase}/{phase.name}"
            )
            return "failed" if outcome.status == "failed" else "success"

        updated = bump_last_touch(manifest, now)
        if updated.wake_up_on is None:
            wake = (now + timedelta(days=7)).isoformat(timespec="milliseconds")
            updated = replace(updated, wake_up_on=wake)
        if verdict == "unverifiable":
            updated = replace(updated, awaiting_human_review=True)
        save_manifest(updated, manifest_path)

    return "not-routed"


def _scope_bypass_context(target: Target, reason: str) -> str:
    lines = [
        f"Scope expansion bypassed: {reason}",
        "Files:",
        *(f"- {file_path}" for file_path in target.files),
    ]
    return "\n".join(lines)


def _expand_target_for_classification(
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


def _route_and_run(
    target: Target,
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
) -> RouteResult:
    live_dir = _resolve_live_migrations_dir(repo_root)
    if live_dir is None:
        return RouteResult(outcome="not-routed", target=target)

    migration_result = _try_migration_tick(
        live_dir, taste, repo_root, artifacts,
        agent=agent, model=model, effort=effort,
        timeout=timeout, commit_message_prefix=commit_message_prefix,
        attempt=attempt,
    )
    if migration_result != "not-routed":
        return RouteResult(outcome=migration_result, target=target)

    target, planning_context = _expand_target_for_classification(
        target,
        taste,
        repo_root,
        artifacts,
        agent=agent,
        model=model,
        effort=effort,
        timeout=timeout,
    )

    decision = classify_target(
        target, taste, repo_root, artifacts,
        agent=agent, model=model, effort=effort, timeout=timeout,
    )
    print(f"Classification: {decision} — {target.description}")

    if decision == "cohesive-cleanup":
        return RouteResult(
            outcome="not-routed",
            target=target,
            planning_context=planning_context,
        )

    migration_name = _migration_name_from_target(target)
    head_before = get_head_sha(repo_root)
    outcome = run_planning(
        migration_name, target.description, taste, repo_root, live_dir, artifacts,
        agent=agent, model=model, effort=effort, timeout=timeout,
        extra_context=planning_context,
    )

    _finalize_commit(
        repo_root,
        head_before,
        f"{commit_message_prefix}: plan {migration_name}",
        artifacts=artifacts,
        attempt=attempt,
        phase="planning",
    )

    print(f"Planning: {_describe_planning_outcome(outcome.status)} — {outcome.reason}")
    return RouteResult(
        outcome="success",
        target=target,
        planning_context=planning_context,
    )


def _describe_planning_outcome(status: str) -> str:
    if status == "ready":
        return "queued for execution"
    if status == "awaiting_human_review":
        return "awaiting human review"
    return status.replace("_", " ")


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


def _max_attempts_exhausted(
    target: Target,
    retry: int,
    max_attempts: int | None,
    *,
    artifacts: RunArtifacts,
    target_index: int,
) -> bool:
    if max_attempts is None or retry < max_attempts:
        return False
    artifacts.log(
        "WARN",
        f"Exhausted {max_attempts} attempts: {target.description}",
        event="max_attempts_exhausted",
        attempt=target_index,
        retry=retry,
    )
    return True


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

        branch_name = prepare_run_branch(
            repo_root,
            args.use_branch,
            generate_run_once_branch_name(),
        )
        artifacts.mark_attempt_started(1)

        route_result = _route_and_run(
            target, taste, repo_root, artifacts,
            agent=args.agent, model=model, effort=effort,
            timeout=timeout,
            commit_message_prefix="continuous refactor",
            attempt=1,
        )
        target = route_result.target
        if route_result.outcome == "success":
            final_status = "completed"
            return 0
        if route_result.outcome == "failed":
            final_status = "migration_failed"
            raise ContinuousRefactorError(
                "Migration phase execution failed"
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

        main_branch = detect_main_branch(repo_root)
        diff_stat = run_command(
            ["git", "diff", f"{main_branch}...HEAD", "--stat"],
            cwd=repo_root,
            check=False,
        )
        print(f"Branch: {branch_name}")
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

    max_refactors = args.max_refactors
    if max_refactors is None and args.targets:
        max_refactors = len(targets)
    if max_refactors and len(targets) > max_refactors:
        targets = random.sample(targets, max_refactors)

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

        branch_name = prepare_run_branch(
            repo_root,
            args.use_branch,
            generate_run_branch_name(),
        )

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

            route_result = _route_and_run(
                target, taste, repo_root, artifacts,
                agent=args.agent, model=model, effort=effort,
                timeout=timeout,
                commit_message_prefix=args.commit_message_prefix,
                attempt=target_index,
            )
            target = route_result.target
            if route_result.outcome == "success":
                consecutive_failures = 0
                _sleep_between_targets(
                    sleep_seconds,
                    artifacts=artifacts,
                    target_index=target_index,
                    total_targets=total_targets,
                )
                continue
            if route_result.outcome == "failed":
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

            previous_failure: str | None = None
            target_succeeded = False
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
                    previous_failure=previous_failure,
                    fix_amendment=fix_amendment_text if retry > 1 else None,
                )

                discard_workspace_changes(repo_root)
                head_before = get_head_sha(repo_root)

                print(
                    f"\nTarget {target_index} attempt {retry}: {target.description}"
                )

                attempt_dir = artifacts.attempt_dir(target_index, retry=retry) / "refactor"
                last_message_path = (
                    attempt_dir / "agent-last-message.md"
                    if args.agent == "codex"
                    else None
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
                    revert_to(repo_root, head_before)
                    artifacts.log(
                        "WARN",
                        f"Agent failed: {target.description}",
                        attempt=target_index,
                        retry=retry,
                    )
                    if _max_attempts_exhausted(
                        target,
                        retry,
                        max_attempts_effective,
                        artifacts=artifacts,
                        target_index=target_index,
                    ):
                        break
                    previous_failure = summarize_output(agent_result)
                    continue

                validation_result = run_tests(
                    args.validation_command,
                    repo_root,
                    stdout_path=attempt_dir / "tests.stdout.log",
                    stderr_path=attempt_dir / "tests.stderr.log",
                    mirror_to_terminal=args.show_command_logs,
                )

                if validation_result.returncode != 0:
                    revert_to(repo_root, head_before)
                    artifacts.log(
                        "WARN",
                        f"Validation failed: {target.description}",
                        attempt=target_index,
                        retry=retry,
                    )
                    if _max_attempts_exhausted(
                        target,
                        retry,
                        max_attempts_effective,
                        artifacts=artifacts,
                        target_index=target_index,
                    ):
                        break
                    previous_failure = summarize_output(validation_result)
                    continue

                commit = _finalize_commit(
                    repo_root,
                    head_before,
                    f"{args.commit_message_prefix}: {target.description}",
                    artifacts=artifacts,
                    attempt=target_index,
                    phase="refactor",
                )
                if commit is not None:
                    if not args.no_push:
                        git_push(repo_root, args.push_remote, branch_name)
                        artifacts.record_push(target_index)
                target_succeeded = True
                break

            if target_succeeded:
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
