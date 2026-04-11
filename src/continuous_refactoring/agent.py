from __future__ import annotations

import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path
from shutil import which
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "build_claude_command",
    "build_codex_command",
    "build_command",
    "maybe_run_agent",
    "run_observed_command",
    "run_tests",
    "stream_pipe",
    "summarize_output",
    "write_timestamped_line",
]

from continuous_refactoring.artifacts import (
    CommandCapture,
    ContinuousRefactorError,
    iso_timestamp,
)


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
    mirror_to_terminal: bool = True,
    timeout: int | None = None,
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
        mirror_to_terminal=mirror_to_terminal,
        timeout=timeout,
    )


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


def _terminate_process(process: subprocess.Popen[str]) -> None:
    """SIGTERM then SIGKILL if the process doesn't exit within 5 seconds."""
    try:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    except OSError:
        pass


def run_observed_command(
    command: Sequence[str],
    cwd: Path,
    *,
    stdout_path: Path,
    stderr_path: Path,
    mirror_to_terminal: bool,
    timeout: int | None = None,
    stuck_interval: int = 30,
    stuck_timeout: int = 120,
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
    stop_watchdog = threading.Event()
    stuck_detected = threading.Event()

    def watchdog() -> None:
        last_count = 0
        stale_since: float | None = None
        while not stop_watchdog.wait(timeout=stuck_interval):
            if process.poll() is not None:
                return
            current_count = len(stdout_chunks) + len(stderr_chunks)
            if current_count != last_count:
                last_count = current_count
                stale_since = None
            else:
                if stale_since is None:
                    stale_since = time.monotonic()
                elif time.monotonic() - stale_since >= stuck_timeout:
                    _terminate_process(process)
                    stuck_detected.set()
                    return

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

        watchdog_thread = threading.Thread(target=watchdog, daemon=True)
        watchdog_thread.start()

        timed_out = False
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process(process)
            returncode = process.wait()

        stdout_thread.join()
        stderr_thread.join()
        stop_watchdog.set()
        watchdog_thread.join(timeout=10)
        was_stuck = stuck_detected.is_set()

        if not stdout_chunks:
            write_timestamped_line(stdout_handle, "<no output>")
        if not stderr_chunks:
            write_timestamped_line(stderr_handle, "<no output>")

    if timed_out:
        raise ContinuousRefactorError(
            f"Command timed out after {timeout}s: {' '.join(command)}"
        )
    if was_stuck:
        raise ContinuousRefactorError(
            f"Command killed: no output for {stuck_timeout}s: {' '.join(command)}"
        )

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
    *,
    mirror_to_terminal: bool = False,
) -> CommandCapture:
    return run_observed_command(
        shlex.split(test_command),
        cwd=repo_root,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        mirror_to_terminal=mirror_to_terminal,
    )


def summarize_output(result: CommandCapture | subprocess.CompletedProcess[str]) -> str:
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    lines = (stdout + stderr).splitlines()
    tail = lines[-40:] if lines else []
    return "\n".join(tail)
