from __future__ import annotations

import random
import sys
from itertools import count
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable

__all__ = [
    "attempt_label",
    "attempt_numbers",
    "log_phase_completion",
    "main",
    "normalize_max_attempts",
    "run_baseline_checks",
    "run_fix_attempt",
    "run_loop",
    "run_once",
    "run_refactoring_attempt",
]

from continuous_refactoring.artifacts import (
    CommandCapture,
    ContinuousRefactorError,
    PhaseAttemptResult,
    RunArtifacts,
    create_run_artifacts,
)
from continuous_refactoring.agent import (
    maybe_run_agent,
    run_tests,
    summarize_output,
)
from continuous_refactoring.cli import parse_args
from continuous_refactoring.config import load_taste, resolve_project
from continuous_refactoring.git import (
    checkout_main,
    create_branch,
    current_branch,
    detect_main_branch,
    discard_workspace_changes,
    generate_run_branch_name,
    generate_run_once_branch_name,
    get_head_sha,
    git_commit,
    git_push,
    repo_change_count,
    require_clean_worktree,
    run_command,
    undo_last_commit,
)
from continuous_refactoring.prompts import (
    DEFAULT_FIX_AMENDMENT,
    DEFAULT_REFACTORING_PROMPT,
    compose_full_prompt,
    compose_refactor_prompt,
    describe_target,
    prompt_file_text,
    resolve_phase_target,
)
from continuous_refactoring.targeting import Target, resolve_targets


def normalize_max_attempts(max_attempts: int | None) -> int | None:
    if max_attempts in (None, 0):
        return None
    return max_attempts


def attempt_numbers(max_attempts: int | None) -> range | count[int]:
    if max_attempts is None:
        return count(1)
    return range(1, max_attempts + 1)


def attempt_label(attempt: int, max_attempts: int | None) -> str:
    if max_attempts is None:
        return str(attempt)
    return f"{attempt}/{max_attempts}"


def run_refactoring_attempt(
    agent: str,
    model: str,
    effort: str,
    prompt_text: str,
    attempt: int,
    repo_root: Path,
    run_tests_fn: Callable[..., CommandCapture],
    test_command: str,
    artifacts: RunArtifacts,
) -> PhaseAttemptResult:
    attempt_dir = artifacts.attempt_dir(attempt) / "refactor"
    prompt = compose_refactor_prompt(prompt_text, attempt)
    last_message_path = (
        attempt_dir / "agent-last-message.md" if agent == "codex" else None
    )
    agent_result = maybe_run_agent(
        agent=agent,
        model=model,
        effort=effort,
        prompt=prompt,
        repo_root=repo_root,
        stdout_path=attempt_dir / "agent.stdout.log",
        stderr_path=attempt_dir / "agent.stderr.log",
        last_message_path=last_message_path,
    )
    target = resolve_phase_target(agent_result, last_message_path)
    if agent_result.returncode != 0:
        return PhaseAttemptResult(
            passed=False,
            failure_context=f"agent command failed with code {agent_result.returncode}",
            target=target,
            agent_returncode=agent_result.returncode,
            test_returncode=None,
        )

    test_result = run_tests_fn(
        test_command,
        repo_root,
        stdout_path=attempt_dir / "tests.stdout.log",
        stderr_path=attempt_dir / "tests.stderr.log",
    )
    if test_result.returncode == 0:
        return PhaseAttemptResult(
            passed=True,
            failure_context="",
            target=target,
            agent_returncode=agent_result.returncode,
            test_returncode=test_result.returncode,
        )

    return PhaseAttemptResult(
        passed=False,
        failure_context=summarize_output(test_result),
        target=target,
        agent_returncode=agent_result.returncode,
        test_returncode=test_result.returncode,
    )


def run_fix_attempt(
    agent: str,
    model: str,
    effort: str,
    fix_prompt: str,
    attempt: int,
    failure_context: str,
    repo_root: Path,
    run_tests_fn: Callable[..., CommandCapture],
    test_command: str,
    artifacts: RunArtifacts,
) -> PhaseAttemptResult:
    attempt_dir = artifacts.attempt_dir(attempt) / "fix"
    prompt = compose_refactor_prompt(
        fix_prompt,
        attempt,
        previous_failure=failure_context,
    )
    last_message_path = (
        attempt_dir / "agent-last-message.md" if agent == "codex" else None
    )
    agent_result = maybe_run_agent(
        agent=agent,
        model=model,
        effort=effort,
        prompt=prompt,
        repo_root=repo_root,
        stdout_path=attempt_dir / "agent.stdout.log",
        stderr_path=attempt_dir / "agent.stderr.log",
        last_message_path=last_message_path,
    )
    target = resolve_phase_target(agent_result, last_message_path)
    if agent_result.returncode != 0:
        return PhaseAttemptResult(
            passed=False,
            failure_context=(
                "agent fix command failed with code "
                f"{agent_result.returncode}"
            ),
            target=target,
            agent_returncode=agent_result.returncode,
            test_returncode=None,
        )

    test_result = run_tests_fn(
        test_command,
        repo_root,
        stdout_path=attempt_dir / "tests.stdout.log",
        stderr_path=attempt_dir / "tests.stderr.log",
    )
    if test_result.returncode == 0:
        return PhaseAttemptResult(
            passed=True,
            failure_context="",
            target=target,
            agent_returncode=agent_result.returncode,
            test_returncode=test_result.returncode,
        )

    return PhaseAttemptResult(
        passed=False,
        failure_context=summarize_output(test_result),
        target=target,
        agent_returncode=agent_result.returncode,
        test_returncode=test_result.returncode,
    )


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


def log_phase_completion(
    artifacts: RunArtifacts,
    *,
    attempt: int,
    phase: str,
    outcome: str,
    target: str | None,
    agent_returncode: int,
    test_returncode: int | None,
    change_count: int | None,
) -> None:
    artifacts.record_phase(
        attempt=attempt,
        phase=phase,
        outcome=outcome,
        target=target,
        agent_returncode=agent_returncode,
        test_returncode=test_returncode,
        change_count=change_count,
    )
    target_text = describe_target(target)
    if outcome == "passed_with_changes":
        artifacts.log(
            "INFO",
            f"completed {phase}: {target_text}",
            attempt=attempt,
            phase=phase,
            outcome=outcome,
            target=target,
            change_count=change_count,
        )
        return
    if outcome == "passed_no_changes":
        artifacts.log(
            "WARN",
            f"completed attempted {phase} with 0 changes: {target_text}",
            attempt=attempt,
            phase=phase,
            outcome=outcome,
            target=target,
            change_count=change_count,
        )
        return
    if outcome == "failed_tests":
        artifacts.log(
            "WARN",
            f"{phase} attempt failed tests: {target_text}",
            attempt=attempt,
            phase=phase,
            outcome=outcome,
            target=target,
            test_returncode=test_returncode,
        )
        return
    artifacts.log(
        "WARN",
        f"{phase} agent command failed with code {agent_returncode}: {target_text}",
        attempt=attempt,
        phase=phase,
        outcome=outcome,
        target=target,
        agent_returncode=agent_returncode,
    )


def main(args: argparse.Namespace | None = None) -> int:
    if args is None:
        args = parse_args()
    repo_root = args.repo_root.resolve()
    max_attempts = normalize_max_attempts(args.max_attempts)
    refactoring_prompt = prompt_file_text(args.refactoring_prompt)
    fix_prompt = prompt_file_text(args.fix_prompt)
    artifacts = create_run_artifacts(
        repo_root,
        agent=args.agent,
        model=args.model,
        effort=args.effort,
        test_command=args.validation_command,
    )
    artifacts.log("INFO", f"run artifacts: {artifacts.root}", event="artifacts_ready")
    final_status = "running"
    error_message: str | None = None
    try:
        try:
            require_clean_worktree(repo_root)
        except ContinuousRefactorError:
            final_status = "dirty_worktree"
            raise
        branch = current_branch(repo_root)
        baseline_ok, baseline_context = run_baseline_checks(
            args.validation_command,
            repo_root,
            stdout_path=artifacts.baseline_dir("initial") / "tests.stdout.log",
            stderr_path=artifacts.baseline_dir("initial") / "tests.stderr.log",
        )
        if not baseline_ok:
            final_status = "baseline_failed"
            artifacts.record_baseline_failure()
            raise ContinuousRefactorError(
                "Aborting: pre-existing test failures detected before any refactor.\n"
                f"{baseline_context}"
            )
        artifacts.log("INFO", "baseline checks passed before refactoring loop")

        for attempt in attempt_numbers(max_attempts):
            artifacts.mark_attempt_started(attempt)
            print(f"\nAttempt {attempt_label(attempt, max_attempts)}: refactoring")
            discard_workspace_changes(repo_root)

            refactor_result = run_refactoring_attempt(
                agent=args.agent,
                model=args.model,
                effort=args.effort,
                prompt_text=refactoring_prompt,
                attempt=attempt,
                repo_root=repo_root,
                run_tests_fn=run_tests,
                test_command=args.validation_command,
                artifacts=artifacts,
            )
            if refactor_result.passed:
                change_count = repo_change_count(repo_root)
                outcome = "passed_with_changes" if change_count else "passed_no_changes"
                log_phase_completion(
                    artifacts,
                    attempt=attempt,
                    phase="refactor",
                    outcome=outcome,
                    target=refactor_result.target,
                    agent_returncode=refactor_result.agent_returncode,
                    test_returncode=refactor_result.test_returncode,
                    change_count=change_count,
                )
                if change_count:
                    commit = git_commit(
                        repo_root=repo_root,
                        message=f"{args.commit_message_prefix}: attempt {attempt}",
                    )
                    artifacts.record_commit(attempt, "refactor", commit)
                    artifacts.log(
                        "INFO",
                        f"created commit {commit}",
                        attempt=attempt,
                        phase="refactor",
                    )
                    print(f"Tests passed. Commit: {commit}")
                    if not args.no_push:
                        git_push(repo_root, args.push_remote, branch)
                        artifacts.record_push(attempt)
                        artifacts.log(
                            "INFO",
                            f"pushed {branch} to {args.push_remote}",
                            attempt=attempt,
                            phase="refactor",
                        )
                        print(f"Pushed {branch} to {args.push_remote}")
                continue

            refactor_outcome = (
                "agent_failed"
                if refactor_result.test_returncode is None
                else "failed_tests"
            )
            log_phase_completion(
                artifacts,
                attempt=attempt,
                phase="refactor",
                outcome=refactor_outcome,
                target=refactor_result.target,
                agent_returncode=refactor_result.agent_returncode,
                test_returncode=refactor_result.test_returncode,
                change_count=None,
            )
            print(
                f"Refactor attempt {attempt} did not pass tests:\n"
                f"{refactor_result.failure_context}"
            )
            discard_workspace_changes(repo_root)
            baseline_ok, baseline_context = run_baseline_checks(
                args.validation_command,
                repo_root,
                stdout_path=artifacts.baseline_dir(f"pre-fix-attempt-{attempt:03d}")
                / "tests.stdout.log",
                stderr_path=artifacts.baseline_dir(f"pre-fix-attempt-{attempt:03d}")
                / "tests.stderr.log",
            )
            if not baseline_ok:
                final_status = "baseline_became_dirty"
                artifacts.record_baseline_failure()
                raise ContinuousRefactorError(
                    "Aborting: repository baseline became dirty before retry.\n"
                    f"{baseline_context}"
                )

            print(f"Attempt {attempt_label(attempt, max_attempts)}: fix pass")
            fix_result = run_fix_attempt(
                agent=args.agent,
                model=args.model,
                effort=args.effort,
                fix_prompt=fix_prompt,
                attempt=attempt,
                failure_context=refactor_result.failure_context,
                repo_root=repo_root,
                run_tests_fn=run_tests,
                test_command=args.validation_command,
                artifacts=artifacts,
            )
            if fix_result.passed:
                change_count = repo_change_count(repo_root)
                outcome = "passed_with_changes" if change_count else "passed_no_changes"
                log_phase_completion(
                    artifacts,
                    attempt=attempt,
                    phase="fix",
                    outcome=outcome,
                    target=fix_result.target,
                    agent_returncode=fix_result.agent_returncode,
                    test_returncode=fix_result.test_returncode,
                    change_count=change_count,
                )
                if change_count:
                    commit = git_commit(
                        repo_root=repo_root,
                        message=(
                            f"{args.commit_message_prefix}: attempt {attempt} (fix)"
                        ),
                    )
                    artifacts.record_commit(attempt, "fix", commit)
                    artifacts.log(
                        "INFO",
                        f"created commit {commit}",
                        attempt=attempt,
                        phase="fix",
                    )
                    print(f"Tests passed after fix. Commit: {commit}")
                    if not args.no_push:
                        git_push(repo_root, args.push_remote, branch)
                        artifacts.record_push(attempt)
                        artifacts.log(
                            "INFO",
                            f"pushed {branch} to {args.push_remote}",
                            attempt=attempt,
                            phase="fix",
                        )
                        print(f"Pushed {branch} to {args.push_remote}")
                continue

            fix_outcome = (
                "agent_failed" if fix_result.test_returncode is None else "failed_tests"
            )
            log_phase_completion(
                artifacts,
                attempt=attempt,
                phase="fix",
                outcome=fix_outcome,
                target=fix_result.target,
                agent_returncode=fix_result.agent_returncode,
                test_returncode=fix_result.test_returncode,
                change_count=None,
            )
            print(
                f"Fix attempt {attempt} did not pass tests:\n"
                f"{fix_result.failure_context}"
            )
            discard_workspace_changes(repo_root)
            baseline_ok, baseline_context = run_baseline_checks(
                args.validation_command,
                repo_root,
                stdout_path=artifacts.baseline_dir(f"post-fix-attempt-{attempt:03d}")
                / "tests.stdout.log",
                stderr_path=artifacts.baseline_dir(f"post-fix-attempt-{attempt:03d}")
                / "tests.stderr.log",
            )
            if not baseline_ok:
                final_status = "baseline_not_green_after_fix"
                artifacts.record_baseline_failure()
                raise ContinuousRefactorError(
                    "Aborting: baseline should be green and is not.\n"
                    f"{baseline_context}"
                )

        if max_attempts is not None:
            final_status = "max_attempts_reached"
            artifacts.log(
                "WARN",
                "Reached max attempts. Stopping continuous refactor loop with no "
                "further failures.",
                event="max_attempts_reached",
            )
            return 0
    except ContinuousRefactorError as error:
        if final_status == "running":
            final_status = "failed"
        error_message = str(error)
        raise
    except KeyboardInterrupt:
        final_status = "interrupted"
        artifacts.log(
            "WARN",
            "Interrupted by user. Stopping continuous refactor loop.",
            event="interrupted",
        )
        return 130
    finally:
        if final_status == "running":
            final_status = "completed"
        artifacts.finish(final_status, error_message=error_message)


def _load_taste_safe(repo_root: Path) -> str:
    try:
        project = resolve_project(repo_root)
        return load_taste(project)
    except ContinuousRefactorError:
        return load_taste(None)


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

        checkout_main(repo_root)
        branch_name = generate_run_once_branch_name()
        create_branch(repo_root, branch_name)

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
            head_after = get_head_sha(repo_root)
            if head_after != head_before:
                undo_last_commit(repo_root)
            else:
                discard_workspace_changes(repo_root)
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

    if not targets:
        targets = [_build_target_fallback(args.scope_instruction)]

    base_prompt = _resolve_base_prompt(args)
    fix_prompt_text = (
        prompt_file_text(args.fix_prompt)
        if args.fix_prompt
        else DEFAULT_FIX_AMENDMENT
    )

    artifacts = create_run_artifacts(
        repo_root,
        agent=args.agent,
        model=args.model,
        effort=args.effort,
        test_command=args.validation_command,
    )
    artifacts.log("INFO", f"run artifacts: {artifacts.root}", event="artifacts_ready")

    final_status = "running"
    error_message: str | None = None
    consecutive_failures = 0

    try:
        require_clean_worktree(repo_root)

        checkout_main(repo_root)
        branch_name = generate_run_branch_name()
        create_branch(repo_root, branch_name)

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

        attempt = 0
        for target in targets:
            attempt += 1
            artifacts.mark_attempt_started(attempt)

            model = target.model_override or args.model
            effort = target.effort_override or args.effort

            prompt = compose_full_prompt(
                base_prompt=base_prompt,
                taste=taste,
                target=target,
                scope_instruction=args.scope_instruction,
                validation_command=args.validation_command,
                attempt=attempt,
            )

            head_before = get_head_sha(repo_root)
            discard_workspace_changes(repo_root)

            print(f"\nAttempt {attempt}: refactoring {target.description}")

            attempt_dir = artifacts.attempt_dir(attempt) / "refactor"
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
                consecutive_failures += 1
                artifacts.log(
                    "WARN",
                    f"Agent failed: {target.description}",
                    attempt=attempt,
                )
                if consecutive_failures >= max_consecutive:
                    final_status = "max_consecutive_failures"
                    raise ContinuousRefactorError(
                        f"Stopping: {max_consecutive} consecutive failures"
                    )
                continue

            validation_result = run_tests(
                args.validation_command,
                repo_root,
                stdout_path=attempt_dir / "tests.stdout.log",
                stderr_path=attempt_dir / "tests.stderr.log",
                mirror_to_terminal=args.show_command_logs,
            )

            if validation_result.returncode != 0:
                head_after = get_head_sha(repo_root)
                if head_after != head_before:
                    undo_last_commit(repo_root)
                else:
                    discard_workspace_changes(repo_root)
                consecutive_failures += 1
                artifacts.log(
                    "WARN",
                    f"Validation failed: {target.description}",
                    attempt=attempt,
                )
                if consecutive_failures >= max_consecutive:
                    final_status = "max_consecutive_failures"
                    raise ContinuousRefactorError(
                        f"Stopping: {max_consecutive} consecutive failures"
                    )
                continue

            consecutive_failures = 0
            change_count = repo_change_count(repo_root)
            if change_count:
                commit = git_commit(
                    repo_root,
                    f"{args.commit_message_prefix}: {target.description}",
                )
                artifacts.record_commit(attempt, "refactor", commit)
                print(f"Committed: {commit}")
                if not args.no_push:
                    git_push(repo_root, args.push_remote, branch_name)
                    artifacts.record_push(attempt)

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
