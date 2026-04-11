#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
import threading
from itertools import count
from pathlib import Path
from shutil import which
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

from continuous_refactoring.artifacts import (
    AttemptStats,
    CommandCapture,
    ContinuousRefactorError,
    PhaseAttemptResult,
    RunArtifacts,
    create_run_artifacts,
    default_artifacts_root,
    iso_timestamp,
)
from continuous_refactoring.git import (
    current_branch,
    discard_workspace_changes,
    git_commit,
    git_push,
    repo_change_count,
    repo_has_changes,
    require_clean_worktree,
    run_command,
    workspace_status_lines,
)


CHOSEN_SCOPE_PATTERN = r"(?:chosen_target|chosen_scope)"
REQUIRED_PREAMBLE = (
    "All changes must keep the project in a state where all tests pass. "
    "Do not finish unless the repository is green after your refactor."
)

TARGET_LINE_PATTERN = re.compile(
    rf"^\s*(?:[-*]\s*)?(?:`|\*\*)?{CHOSEN_SCOPE_PATTERN}"
    rf"(?:`|\*\*)?\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)
TARGET_HEADER_PATTERN = re.compile(
    rf"^\s*(?:#+\s*)?(?:`|\*\*)?{CHOSEN_SCOPE_PATTERN}(?:`|\*\*)?\s*:?\s*$",
    re.IGNORECASE,
)
SUMMARY_UNKNOWN = "scope unavailable"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run iterative refactoring prompts with codex or claude.",
    )
    parser.add_argument(
        "--agent",
        choices=("codex", "claude"),
        required=True,
        help="Coding agent to run: codex or claude.",
    )
    parser.add_argument(
        "--model",
        required=True,
        help="Model name for the selected agent.",
    )
    parser.add_argument(
        "--effort",
        required=True,
        help="Effort level passed to the selected agent (e.g., xhigh/max).",
    )
    parser.add_argument(
        "--refactoring-prompt",
        required=True,
        type=Path,
        help="Prompt file used for the primary refactoring pass.",
    )
    parser.add_argument(
        "--fix-prompt",
        required=True,
        type=Path,
        help="Prompt file used after a failed test run before retrying.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root for all commands.",
    )
    parser.add_argument(
        "--test-command",
        default="uv run pytest",
        help="Command used to run the full test suite.",
    )
    parser.add_argument(
        "--max-attempts",
        type=parse_max_attempts,
        default=None,
        help=(
            "Maximum attempt cycles before stopping. "
            "Omit or use 0 to run until interrupted."
        ),
    )
    parser.add_argument(
        "--commit-message-prefix",
        default="continuous refactor",
        help="Prefix for the commit message.",
    )
    parser.add_argument(
        "--push-remote",
        default="origin",
        help="Git remote for pushing.",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Run the loop and commit without pushing.",
    )
    return parser.parse_args()


def parse_max_attempts(value: str) -> int:
    try:
        attempts = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    if attempts < 0:
        raise argparse.ArgumentTypeError("--max-attempts must be >= 0")
    return attempts


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


def write_timestamped_line(handle: TextIO, line: str) -> None:
    suffix = "" if line.endswith("\n") else "\n"
    handle.write(f"[{iso_timestamp()}] {line}{suffix}")
    handle.flush()


def stream_pipe(
    pipe: TextIO,
    sink: TextIO,
    mirror: TextIO | None,
    chunks: list[str],
) -> None:
    for line in pipe:
        chunks.append(line)
        write_timestamped_line(sink, line)
        if mirror is not None:
            mirror.write(line)
            mirror.flush()
    pipe.close()


def run_observed_command(
    command: Sequence[str],
    cwd: Path,
    *,
    stdout_path: Path,
    stderr_path: Path,
    mirror_to_terminal: bool,
) -> CommandCapture:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        command,
        cwd=cwd,
        text=True,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
    )
    if process.stdout is None or process.stderr is None:
        raise ContinuousRefactorError(
            f"Failed to capture process output for command: {' '.join(command)}"
        )

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    with (
        stdout_path.open("w", encoding="utf-8") as stdout_handle,
        stderr_path.open("w", encoding="utf-8") as stderr_handle,
    ):
        stdout_thread = threading.Thread(
            target=stream_pipe,
            args=(
                process.stdout,
                stdout_handle,
                sys.stdout if mirror_to_terminal else None,
                stdout_chunks,
            ),
        )
        stderr_thread = threading.Thread(
            target=stream_pipe,
            args=(
                process.stderr,
                stderr_handle,
                sys.stderr if mirror_to_terminal else None,
                stderr_chunks,
            ),
        )
        stdout_thread.start()
        stderr_thread.start()
        returncode = process.wait()
        stdout_thread.join()
        stderr_thread.join()
        if not stdout_chunks:
            write_timestamped_line(stdout_handle, "<no output>")
        if not stderr_chunks:
            write_timestamped_line(stderr_handle, "<no output>")

    return CommandCapture(
        command=tuple(command),
        returncode=returncode,
        stdout="".join(stdout_chunks),
        stderr="".join(stderr_chunks),
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )


def run_tests(
    test_command: str,
    repo_root: Path,
    stdout_path: Path,
    stderr_path: Path,
) -> CommandCapture:
    return run_observed_command(
        shlex.split(test_command),
        cwd=repo_root,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        mirror_to_terminal=False,
    )


def prompt_file_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def build_codex_command(
    model: str,
    effort: str,
    prompt: str,
    repo_root: Path,
    *,
    last_message_path: Path,
) -> list[str]:
    return [
        "codex",
        "exec",
        "--model",
        model,
        "--config",
        f"model_reasoning_effort={effort}",
        "--dangerously-bypass-approvals-and-sandbox",
        "--output-last-message",
        str(last_message_path),
        "--cd",
        str(repo_root),
        prompt,
    ]


def build_claude_command(
    model: str,
    effort: str,
    prompt: str,
    _repo_root: Path,
) -> list[str]:
    return [
        "claude",
        "--print",
        "--model",
        model,
        "--effort",
        effort,
        "--permission-mode",
        "bypassPermissions",
        "--output-format",
        "text",
        prompt,
    ]


def build_command(
    agent: str,
    model: str,
    effort: str,
    prompt: str,
    repo_root: Path,
    *,
    last_message_path: Path | None = None,
) -> list[str]:
    if agent == "codex":
        if last_message_path is None:
            raise ContinuousRefactorError(
                "Codex runs require a last-message artifact path."
            )
        return build_codex_command(
            model=model,
            effort=effort,
            prompt=prompt,
            repo_root=repo_root,
            last_message_path=last_message_path,
        )
    return build_claude_command(model, effort, prompt, repo_root)


def compose_refactor_prompt(
    base_prompt: str,
    attempt: int,
    previous_failure: str | None = None,
) -> str:
    sections = [
        f"Attempt {attempt}",
        base_prompt,
        REQUIRED_PREAMBLE,
    ]
    if previous_failure:
        sections.append("Previous attempt failed tests with this output:\n")
        sections.append(previous_failure)
        sections.append(
            "Use this as context only if it helps; do not copy test output into code."
        )
        sections.append(
            "Only fix failures introduced by this refactoring pass. "
            "If a failure is not a direct consequence of your edits, "
            "do not rewrite unrelated code."
        )
    return "\n\n".join(sections)


def normalize_target(text: str) -> str:
    return " ".join(text.strip().strip("`*").split())


def extract_chosen_target(text: str) -> str | None:
    lines = text.splitlines()
    for line in lines:
        match = TARGET_LINE_PATTERN.match(line)
        if match:
            return normalize_target(match.group(1))

    for index, line in enumerate(lines):
        if not TARGET_HEADER_PATTERN.match(line):
            continue
        for candidate in lines[index + 1 :]:
            stripped = candidate.strip()
            if not stripped:
                continue
            if stripped.startswith(("-", "*")):
                stripped = stripped[1:].strip()
            return normalize_target(stripped)
    return None


def maybe_run_agent(
    agent: str,
    model: str,
    effort: str,
    prompt: str,
    repo_root: Path,
    *,
    stdout_path: Path,
    stderr_path: Path,
    last_message_path: Path | None = None,
) -> CommandCapture:
    if which(agent) is None:
        raise ContinuousRefactorError(f"Required command not found in PATH: {agent}")

    command = build_command(
        agent=agent,
        model=model,
        effort=effort,
        prompt=prompt,
        repo_root=repo_root,
        last_message_path=last_message_path,
    )
    return run_observed_command(
        command,
        cwd=repo_root,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        mirror_to_terminal=True,
    )


def summarize_output(result: CommandCapture | subprocess.CompletedProcess[str]) -> str:
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    lines = (stdout + stderr).splitlines()
    tail = lines[-40:] if lines else []
    return "\n".join(tail)


def resolve_phase_target(
    agent_result: CommandCapture,
    last_message_path: Path | None,
) -> str | None:
    if last_message_path is not None and last_message_path.exists():
        target = extract_chosen_target(last_message_path.read_text(encoding="utf-8"))
        if target:
            return target
    return extract_chosen_target(agent_result.stdout) or extract_chosen_target(
        agent_result.stderr
    )


def describe_target(target: str | None) -> str:
    return target or SUMMARY_UNKNOWN


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
        test_command=args.test_command,
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
            args.test_command,
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
                test_command=args.test_command,
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
                args.test_command,
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
                test_command=args.test_command,
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
                args.test_command,
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


def cli_main() -> None:
    try:
        raise SystemExit(main())
    except ContinuousRefactorError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
