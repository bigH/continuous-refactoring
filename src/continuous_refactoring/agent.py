from __future__ import annotations

import hashlib
import json
import signal
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from shutil import which
from typing import TYPE_CHECKING, TextIO

try:
    import termios
except ImportError:  # pragma: no cover - termios is unavailable on Windows.
    termios = None

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "build_command",
    "maybe_run_agent",
    "run_agent_interactive",
    "run_agent_interactive_until_settled",
    "run_observed_command",
    "run_tests",
    "summarize_output",
]

from continuous_refactoring.artifacts import (
    CommandCapture,
    ContinuousRefactorError,
    iso_timestamp,
)


def _require_supported_agent(agent: str) -> None:
    if agent not in {"codex", "claude"}:
        raise ContinuousRefactorError(f"Unsupported agent backend: {agent}")


def _build_claude_command(
    model: str,
    effort: str,
    prompt: str,
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
        "--verbose",
        "--output-format",
        "stream-json",
        "--include-partial-messages",
        prompt,
    ]


def _extract_claude_final_text(raw: str) -> str:
    """Pull plain-text output from claude's ``--output-format stream-json`` stream.

    Claude emits NDJSON events. Prefer the last valid top-level ``result``
    string; otherwise join assistant text blocks; otherwise return ``raw``
    unchanged so upstream errors like "produced no output" stay meaningful.
    """
    last_result: str | None = None
    assistant_messages: list[str] = []
    for line in raw.splitlines():
        if not line.lstrip().startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "result":
            if event.get("is_error") is True:
                continue
            result = event.get("result")
            if isinstance(result, str) and result:
                last_result = result
            continue
        if event.get("type") != "assistant":
            continue
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        parts = [
            text
            for block in content
            if isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(text := block.get("text"), str)
            and text
        ]
        if parts:
            assistant_messages.append("".join(parts))
    if last_result is not None:
        return last_result
    if assistant_messages:
        return "\n".join(assistant_messages)
    return raw


def _require_agent_on_path(agent: str) -> None:
    _require_supported_agent(agent)
    if which(agent) is None:
        raise ContinuousRefactorError(f"Required command not found in PATH: {agent}")


def _build_interactive_command(
    agent: str,
    model: str,
    effort: str,
    prompt: str,
    repo_root: Path,
) -> list[str]:
    _require_supported_agent(agent)
    if agent == "codex":
        return _build_codex_interactive_command(model, effort, prompt, repo_root)
    return _build_claude_interactive_command(model, effort, prompt)


def _build_codex_command(
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


def build_command(
    agent: str,
    model: str,
    effort: str,
    prompt: str,
    repo_root: Path,
    *,
    last_message_path: Path | None = None,
) -> list[str]:
    _require_supported_agent(agent)
    if agent == "codex":
        if last_message_path is None:
            raise ContinuousRefactorError(
                "Codex runs require a last-message artifact path."
            )
        return _build_codex_command(
            model=model,
            effort=effort,
            prompt=prompt,
            repo_root=repo_root,
            last_message_path=last_message_path,
        )
    return _build_claude_command(model, effort, prompt)


def _build_codex_interactive_command(
    model: str,
    effort: str,
    prompt: str,
    repo_root: Path,
) -> list[str]:
    return [
        "codex",
        "--model",
        model,
        "--config",
        f"model_reasoning_effort={effort}",
        "--dangerously-bypass-approvals-and-sandbox",
        "--cd",
        str(repo_root),
        prompt,
    ]


def _build_claude_interactive_command(
    model: str,
    effort: str,
    prompt: str,
) -> list[str]:
    return [
        "claude",
        "--model",
        model,
        "--effort",
        effort,
        "--permission-mode",
        "bypassPermissions",
        prompt,
    ]


def run_agent_interactive(
    agent: str,
    model: str,
    effort: str,
    prompt: str,
    repo_root: Path,
) -> int:
    """Exec the agent attached to the user's terminal. Returns exit code."""
    _require_agent_on_path(agent)
    command = _build_interactive_command(agent, model, effort, prompt, repo_root)
    terminal_fd = _terminal_control_fd()
    terminal_state = _capture_terminal_state(terminal_fd)
    try:
        return subprocess.call(command, cwd=repo_root)
    finally:
        _restore_terminal_state(terminal_fd, terminal_state)


def _read_sha256(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return hashlib.sha256(data).hexdigest()


def _read_settle_digest(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    prefix = "sha256:"
    if not text.startswith(prefix):
        return None
    digest = text[len(prefix):].strip().lower()
    if len(digest) != 64:
        return None
    if any(char not in "0123456789abcdef" for char in digest):
        return None
    return digest


def _interactive_settle_fingerprint(
    content_path: Path,
    settle_path: Path,
) -> tuple[str, int, int, int, int] | None:
    expected_digest = _read_settle_digest(settle_path)
    if expected_digest is None:
        return None
    actual_digest = _read_sha256(content_path)
    if actual_digest != expected_digest:
        return None
    try:
        content_stat = content_path.stat()
        settle_stat = settle_path.stat()
    except OSError:
        return None
    return (
        actual_digest,
        content_stat.st_size,
        content_stat.st_mtime_ns,
        settle_stat.st_size,
        settle_stat.st_mtime_ns,
    )


def _send_signal_and_wait_for_exit(
    process: subprocess.Popen[object],
    signal_to_send: int,
    *,
    timeout: float,
) -> bool:
    if process.poll() is not None:
        return True

    try:
        process.send_signal(signal_to_send)
    except (OSError, ValueError):
        return process.poll() is not None

    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return process.poll() is not None
    return True


def _terminal_control_fd() -> int | None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            if stream.isatty():
                return stream.fileno()
        except (AttributeError, OSError, ValueError):
            continue
    return None


def _capture_terminal_state(fd: int | None) -> object | None:
    if fd is None or termios is None:
        return None
    try:
        return termios.tcgetattr(fd)
    except (termios.error, OSError, ValueError):
        return None


def _restore_terminal_state(fd: int | None, state: object | None) -> None:
    if fd is None or state is None or termios is None:
        return
    try:
        termios.tcsetattr(fd, termios.TCSADRAIN, state)
    except (termios.error, OSError, ValueError):
        pass


_FORCED_CODEX_TERMINAL_RESET = (
    b"\x1b[<u"  # Pop keyboard enhancement flags.
    b"\x1b[?2004l"  # Disable bracketed paste.
    b"\x1b[?1004l"  # Disable focus reporting.
    b"\x1b[>4m"  # Disable modifyOtherKeys.
    b"\x1b[?25h"  # Show cursor.
)


def _restore_codex_terminal_modes_after_forced_stop() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            if not stream.isatty():
                continue
            buffer = getattr(stream, "buffer", None)
            if buffer is not None:
                buffer.write(_FORCED_CODEX_TERMINAL_RESET)
                buffer.flush()
                return
            stream.write(_FORCED_CODEX_TERMINAL_RESET.decode("ascii"))
            stream.flush()
            return
        except (AttributeError, OSError, ValueError):
            continue

    try:
        with open("/dev/tty", "wb", buffering=0) as tty:
            tty.write(_FORCED_CODEX_TERMINAL_RESET)
    except OSError:
        pass


def _flush_terminal_input(fd: int | None) -> None:
    if fd is None or termios is None:
        return
    try:
        termios.tcflush(fd, termios.TCIFLUSH)
    except (termios.error, OSError, ValueError):
        pass


def _gracefully_stop_interactive_process(
    process: subprocess.Popen[object],
    *,
    interrupt_timeout: float = 1.0,
    terminate_timeout: float = 2.0,
) -> None:
    if _send_signal_and_wait_for_exit(
        process,
        signal.SIGINT,
        timeout=interrupt_timeout,
    ):
        return

    if _send_signal_and_wait_for_exit(
        process,
        signal.SIGTERM,
        timeout=terminate_timeout,
    ):
        return

    try:
        process.kill()
    except OSError:
        pass
    try:
        process.wait()
    except OSError:
        pass


def run_agent_interactive_until_settled(
    agent: str,
    model: str,
    effort: str,
    prompt: str,
    repo_root: Path,
    *,
    content_path: Path,
    settle_path: Path,
    settle_window_seconds: float = 2.0,
    poll_interval_seconds: float = 0.1,
) -> int:
    _require_agent_on_path(agent)

    settle_path.parent.mkdir(parents=True, exist_ok=True)
    if settle_path.exists():
        if settle_path.is_dir():
            raise ContinuousRefactorError(f"Settle path is a directory: {settle_path}")
        settle_path.unlink()

    command = _build_interactive_command(agent, model, effort, prompt, repo_root)
    terminal_fd = _terminal_control_fd()
    terminal_state = _capture_terminal_state(terminal_fd)
    process = subprocess.Popen(command, cwd=repo_root)
    settled_since: float | None = None
    last_fingerprint: tuple[str, int, int, int, int] | None = None
    forced_codex_stop = False

    try:
        while True:
            fingerprint = _interactive_settle_fingerprint(content_path, settle_path)
            if fingerprint is None:
                settled_since = None
                last_fingerprint = None
            elif fingerprint != last_fingerprint:
                last_fingerprint = fingerprint
                settled_since = time.monotonic()
            elif settled_since is not None:
                elapsed = time.monotonic() - settled_since
                if elapsed >= settle_window_seconds:
                    returncode = process.poll()
                    if returncode is not None:
                        return returncode
                    forced_codex_stop = agent == "codex"
                    _gracefully_stop_interactive_process(process)
                    return 0

            returncode = process.poll()
            if returncode is not None:
                if fingerprint is not None:
                    return returncode
                raise ContinuousRefactorError(
                    "interactive agent exited before the settled write was confirmed"
                )

            time.sleep(poll_interval_seconds)
    finally:
        if forced_codex_stop:
            _restore_codex_terminal_modes_after_forced_stop()
        _restore_terminal_state(terminal_fd, terminal_state)
        if forced_codex_stop:
            _flush_terminal_input(terminal_fd)


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
    _require_agent_on_path(agent)
    command = build_command(
        agent=agent,
        model=model,
        effort=effort,
        prompt=prompt,
        repo_root=repo_root,
        last_message_path=last_message_path,
    )
    capture = run_observed_command(
        command,
        cwd=repo_root,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        mirror_to_terminal=mirror_to_terminal,
        timeout=timeout,
    )
    if agent == "claude":
        return replace(capture, stdout=_extract_claude_final_text(capture.stdout))
    return capture


def _write_timestamped_line(handle: TextIO, line: str) -> None:
    suffix = "" if line.endswith("\n") else "\n"
    handle.write(f"[{iso_timestamp()}] {line}{suffix}")
    handle.flush()


def _stream_pipe(
    pipe: TextIO,
    sink: TextIO,
    mirror: TextIO | None,
    chunks: list[str],
) -> None:
    for line in pipe:
        chunks.append(line)
        _write_timestamped_line(sink, line)
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


def _command_display_name(command: Sequence[str]) -> str:
    return Path(command[0]).name or str(command[0])


@dataclass(frozen=True)
class _ObservedCommandOutcome:
    returncode: int
    timed_out: bool
    was_stuck: bool


def _wait_for_observed_command(
    process: subprocess.Popen[str],
    *,
    timeout: int | None,
    stdout_thread: threading.Thread,
    stderr_thread: threading.Thread,
    stop_watchdog: threading.Event,
    watchdog_thread: threading.Thread,
    stuck_detected: threading.Event,
) -> _ObservedCommandOutcome:
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

    return _ObservedCommandOutcome(
        returncode=returncode,
        timed_out=timed_out,
        was_stuck=stuck_detected.is_set(),
    )


def run_observed_command(
    command: Sequence[str],
    cwd: Path,
    *,
    stdout_path: Path,
    stderr_path: Path,
    mirror_to_terminal: bool,
    timeout: int | None = None,
    stuck_interval: int = 30,
    stuck_timeout: int = 300,
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
        command_name = _command_display_name(command)
        raise ContinuousRefactorError(
            f"Failed to capture process output for {command_name}"
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
            target=_stream_pipe,
            args=(
                process.stdout,
                stdout_handle,
                sys.stdout if mirror_to_terminal else None,
                stdout_chunks,
            ),
        )
        stderr_thread = threading.Thread(
            target=_stream_pipe,
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

        outcome = _wait_for_observed_command(
            process,
            timeout=timeout,
            stdout_thread=stdout_thread,
            stderr_thread=stderr_thread,
            stop_watchdog=stop_watchdog,
            watchdog_thread=watchdog_thread,
            stuck_detected=stuck_detected,
        )

        if not stdout_chunks:
            _write_timestamped_line(stdout_handle, "<no output>")
        if not stderr_chunks:
            _write_timestamped_line(stderr_handle, "<no output>")

    if outcome.timed_out:
        command_name = _command_display_name(command)
        raise ContinuousRefactorError(f"{command_name} timed out after {timeout}s")
    if outcome.was_stuck:
        command_name = _command_display_name(command)
        raise ContinuousRefactorError(
            f"{command_name} produced no output for {stuck_timeout}s"
        )

    return CommandCapture(
        command=tuple(command),
        returncode=outcome.returncode,
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


def summarize_output(result: CommandCapture) -> str:
    lines = (result.stdout + result.stderr).splitlines()
    return "\n".join(lines[-40:])
