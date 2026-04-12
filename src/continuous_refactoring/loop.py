from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

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
from continuous_refactoring.config import load_taste, resolve_project
from continuous_refactoring.git import (
    checkout_main,
    create_branch,
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
    DEFAULT_REFACTORING_PROMPT,
    compose_full_prompt,
    prompt_file_text,
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
