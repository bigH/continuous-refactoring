from __future__ import annotations

import sys
from itertools import count
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

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
from continuous_refactoring.git import (
    current_branch,
    discard_workspace_changes,
    git_commit,
    git_push,
    repo_change_count,
    require_clean_worktree,
)
from continuous_refactoring.prompts import (
    compose_refactor_prompt,
    describe_target,
    prompt_file_text,
    resolve_phase_target,
)


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


def main() -> int:
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
