from __future__ import annotations

import random
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

    from continuous_refactoring.artifacts import RunArtifacts

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
    detect_main_branch,
    discard_workspace_changes,
    generate_run_branch_name,
    generate_run_once_branch_name,
    get_head_sha,
    git_commit,
    git_push,
    prepare_run_branch,
    repo_change_count,
    require_clean_worktree,
    revert_to,
    run_command,
)
from continuous_refactoring.planning import run_planning
from continuous_refactoring.prompts import (
    DEFAULT_FIX_AMENDMENT,
    DEFAULT_REFACTORING_PROMPT,
    compose_full_prompt,
    prompt_file_text,
)
from continuous_refactoring.routing import classify_target
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
    from datetime import datetime

    slug = re.sub(r"[^a-z0-9]+", "-", target.description.lower()).strip("-")
    ts = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")
    prefix = slug[:40] if slug else "migration"
    return f"{prefix}-{ts}"


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
) -> bool:
    live_dir = _resolve_live_migrations_dir(repo_root)
    if live_dir is None:
        return False

    decision = classify_target(
        target, taste, repo_root, artifacts,
        agent=agent, model=model, effort=effort, timeout=timeout,
    )
    print(f"Classification: {decision} — {target.description}")

    if decision == "cohesive-cleanup":
        return False

    migration_name = _migration_name_from_target(target)
    outcome = run_planning(
        migration_name, target.description, taste, repo_root, live_dir, artifacts,
        agent=agent, model=model, effort=effort, timeout=timeout,
    )

    if repo_change_count(repo_root):
        git_commit(repo_root, f"{commit_message_prefix}: plan {migration_name}")

    print(f"Planning: {outcome.status} — {outcome.reason}")
    return True


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


def run_once(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    timeout = args.timeout or 900
    taste = _load_taste_safe(repo_root)

    paths = tuple(args.paths.split(":")) if args.paths else None
    targets = resolve_targets(
        extensions=args.extensions,
        globs=args.globs,
        targets_path=args.targets,
        paths=paths,
        repo_root=repo_root,
    )
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

        if _route_and_run(
            target, taste, repo_root, artifacts,
            agent=args.agent, model=model, effort=effort,
            timeout=timeout,
            commit_message_prefix="continuous refactor",
        ):
            final_status = "completed"
            return 0

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

        change_count = repo_change_count(repo_root)
        if change_count:
            git_commit(repo_root, "continuous refactor: run-once")

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
    max_consecutive = args.max_consecutive_failures
    max_attempts_effective = _effective_max_attempts(
        getattr(args, "max_attempts", None)
    )
    taste = _load_taste_safe(repo_root)

    paths = tuple(args.paths.split(":")) if args.paths else None
    targets = resolve_targets(
        extensions=args.extensions,
        globs=args.globs,
        targets_path=args.targets,
        paths=paths,
        repo_root=repo_root,
    )

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

        target_index = 0
        for target in targets:
            target_index += 1
            artifacts.mark_attempt_started(target_index)

            model = target.model_override or args.model
            effort = target.effort_override or args.effort

            if _route_and_run(
                target, taste, repo_root, artifacts,
                agent=args.agent, model=model, effort=effort,
                timeout=timeout,
                commit_message_prefix=args.commit_message_prefix,
            ):
                consecutive_failures = 0
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
                    if (
                        max_attempts_effective is not None
                        and retry >= max_attempts_effective
                    ):
                        artifacts.log(
                            "WARN",
                            f"Exhausted {max_attempts_effective} attempts: "
                            f"{target.description}",
                            event="max_attempts_exhausted",
                            attempt=target_index,
                            retry=retry,
                        )
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
                    if (
                        max_attempts_effective is not None
                        and retry >= max_attempts_effective
                    ):
                        artifacts.log(
                            "WARN",
                            f"Exhausted {max_attempts_effective} attempts: "
                            f"{target.description}",
                            event="max_attempts_exhausted",
                            attempt=target_index,
                            retry=retry,
                        )
                        break
                    previous_failure = summarize_output(validation_result)
                    continue

                change_count = repo_change_count(repo_root)
                if change_count:
                    commit = git_commit(
                        repo_root,
                        f"{args.commit_message_prefix}: {target.description}",
                    )
                    artifacts.record_commit(target_index, "refactor", commit)
                    print(f"Committed: {commit}")
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
