from __future__ import annotations

import ast
import hashlib
import io
import os
from datetime import datetime, timezone
import re
import sys
import time
from pathlib import Path

import pytest

import continuous_refactoring
import continuous_refactoring.migration_manifest_codec as migration_manifest_codec
import continuous_refactoring.artifacts as artifacts
from continuous_refactoring.artifacts import ContinuousRefactorError, create_run_artifacts
from continuous_refactoring.migrations import (
    MigrationManifest,
    PhaseSpec,
    load_manifest,
    save_manifest,
)
from continuous_refactoring.targeting import Target


def test_run_observed_command_writes_timestamped_logs(tmp_path: Path) -> None:
    stdout_path = tmp_path / "observed.stdout.log"
    stderr_path = tmp_path / "observed.stderr.log"

    result = continuous_refactoring.run_observed_command(
        [sys.executable, "-c", "print('hello from stdout')"],
        cwd=tmp_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        mirror_to_terminal=False,
    )

    assert result.returncode == 0
    assert result.stdout == "hello from stdout\n"
    assert result.stderr == ""
    assert re.search(r"^\[\d{4}-\d{2}-\d{2}T", stdout_path.read_text(encoding="utf-8"))
    assert "hello from stdout" in stdout_path.read_text(encoding="utf-8")
    assert "<no output>" in stderr_path.read_text(encoding="utf-8")


def test_run_observed_command_timeout_hides_full_command_text(tmp_path: Path) -> None:
    stdout_path = tmp_path / "out.log"
    stderr_path = tmp_path / "err.log"
    secret = "VERY-HUGE-PROMPT-TEXT"

    with pytest.raises(ContinuousRefactorError) as error:
        continuous_refactoring.run_observed_command(
            [sys.executable, "-c", "import time; time.sleep(60)", secret],
            cwd=tmp_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            mirror_to_terminal=False,
            timeout=1,
        )

    message = str(error.value)
    assert "timed out" in message
    assert secret not in message
    assert "python" in message


def test_run_observed_command_stuck_hides_full_command_text(tmp_path: Path) -> None:
    stdout_path = tmp_path / "out.log"
    stderr_path = tmp_path / "err.log"
    secret = "VERY-HUGE-PROMPT-TEXT"
    script = "import sys, time; print('hello'); sys.stdout.flush(); time.sleep(60)"

    with pytest.raises(ContinuousRefactorError) as error:
        continuous_refactoring.run_observed_command(
            [sys.executable, "-c", script, secret],
            cwd=tmp_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            mirror_to_terminal=False,
            stuck_interval=1,
            stuck_timeout=2,
        )

    message = str(error.value)
    assert "produced no output" in message
    assert secret not in message
    assert "python" in message


def test_package_exports_are_stable() -> None:
    assert isinstance(continuous_refactoring.__all__, tuple)
    assert len(continuous_refactoring.__all__) == len(set(continuous_refactoring.__all__))
    for name in (
        "AttemptStats",
        "build_command",
        "run_observed_command",
        "run_command",
        "bump_last_touch",
        "check_phase_ready",
        "PlanningOutcome",
        "compose_full_prompt",
        "ClassifierDecision",
        "run_once",
        "cli_main",
    ):
        assert hasattr(continuous_refactoring, name)


def test_migration_manifest_codec_stays_internal() -> None:
    assert MigrationManifest.__name__ == "MigrationManifest"
    assert PhaseSpec.__name__ == "PhaseSpec"
    assert callable(load_manifest)
    assert callable(save_manifest)
    assert callable(migration_manifest_codec.decode_manifest_payload)
    assert callable(migration_manifest_codec.encode_manifest_payload)
    assert not hasattr(continuous_refactoring, "decode_manifest_payload")
    assert not hasattr(continuous_refactoring, "encode_manifest_payload")
    assert migration_manifest_codec.__name__ not in {
        module.__name__ for module in continuous_refactoring._SUBMODULES
    }


def test_package_init_follows_source_import_conventions() -> None:
    init_path = Path(continuous_refactoring.__file__)
    source = init_path.read_text(encoding="utf-8")
    relative_imports = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
        and node.level > 0
    ]

    assert source.startswith("from __future__ import annotations\n")
    assert relative_imports == []


def test_build_command_claude_streams_json_so_watchdog_sees_progress() -> None:
    command = continuous_refactoring.build_command(
        "claude", "opus", "medium", "do the thing", Path("/repo"),
    )

    assert command[:2] == ["claude", "--print"]
    assert "--verbose" in command
    assert "--include-partial-messages" in command
    fmt_index = command.index("--output-format")
    assert command[fmt_index + 1] == "stream-json"


def test_build_command_rejects_unknown_agent() -> None:
    with pytest.raises(ContinuousRefactorError, match="Unsupported agent backend"):
        continuous_refactoring.build_command(
            "gemini",
            "opus",
            "medium",
            "do the thing",
            Path("/repo"),
        )


def test_maybe_run_agent_rejects_unknown_agent_before_path_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path_lookups: list[str] = []
    monkeypatch.setattr(
        "continuous_refactoring.agent.which",
        lambda agent: path_lookups.append(agent) or None,
    )

    with pytest.raises(ContinuousRefactorError, match="Unsupported agent backend"):
        continuous_refactoring.maybe_run_agent(
            "gemini",
            "opus",
            "medium",
            "do the thing",
            tmp_path,
            stdout_path=tmp_path / "stdout.log",
            stderr_path=tmp_path / "stderr.log",
        )

    assert path_lookups == []


def test_run_agent_interactive_rejects_unknown_agent_before_path_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path_lookups: list[str] = []
    monkeypatch.setattr(
        "continuous_refactoring.agent.which",
        lambda agent: path_lookups.append(agent) or None,
    )

    with pytest.raises(ContinuousRefactorError, match="Unsupported agent backend"):
        continuous_refactoring.run_agent_interactive(
            "gemini",
            "opus",
            "medium",
            "do the thing",
            tmp_path,
        )

    assert path_lookups == []


def test_interactive_settle_rejects_unknown_agent_before_settle_path_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path_lookups: list[str] = []
    settle_path = tmp_path / "taste.md.done"
    settle_path.mkdir()
    monkeypatch.setattr(
        "continuous_refactoring.agent.which",
        lambda agent: path_lookups.append(agent) or None,
    )

    with pytest.raises(ContinuousRefactorError, match="Unsupported agent backend"):
        continuous_refactoring.run_agent_interactive_until_settled(
            "gemini",
            "opus",
            "medium",
            "do the thing",
            tmp_path,
            content_path=tmp_path / "taste.md",
            settle_path=settle_path,
        )

    assert path_lookups == []


class _FakeInteractiveProcess:
    def __init__(
        self,
        *,
        exit_on_signal: int | None = None,
        returncode: int | None = None,
    ) -> None:
        self.exit_on_signal = exit_on_signal
        self.returncode = returncode
        self.signals: list[int] = []
        self.wait_timeouts: list[float | None] = []
        self.kill_calls = 0

    def poll(self) -> int | None:
        return self.returncode

    def send_signal(self, signal_to_send: int) -> None:
        self.signals.append(signal_to_send)
        if signal_to_send == self.exit_on_signal:
            self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        self.wait_timeouts.append(timeout)
        if self.returncode is None:
            raise continuous_refactoring.agent.subprocess.TimeoutExpired(
                cmd="fake-agent",
                timeout=timeout,
            )
        return self.returncode

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9


def test_gracefully_stop_interactive_process_skips_finished_process() -> None:
    process = _FakeInteractiveProcess(returncode=0)

    continuous_refactoring.agent._gracefully_stop_interactive_process(process)

    assert process.signals == []
    assert process.wait_timeouts == []
    assert process.kill_calls == 0


def test_gracefully_stop_interactive_process_stops_after_sigint_exit() -> None:
    process = _FakeInteractiveProcess(
        exit_on_signal=continuous_refactoring.agent.signal.SIGINT,
    )

    continuous_refactoring.agent._gracefully_stop_interactive_process(
        process,
        interrupt_timeout=1.5,
        terminate_timeout=2.5,
    )

    assert process.signals == [continuous_refactoring.agent.signal.SIGINT]
    assert process.wait_timeouts == [1.5]
    assert process.kill_calls == 0


def test_gracefully_stop_interactive_process_escalates_to_sigterm() -> None:
    process = _FakeInteractiveProcess(
        exit_on_signal=continuous_refactoring.agent.signal.SIGTERM,
    )

    continuous_refactoring.agent._gracefully_stop_interactive_process(
        process,
        interrupt_timeout=1.0,
        terminate_timeout=2.0,
    )

    assert process.signals == [
        continuous_refactoring.agent.signal.SIGINT,
        continuous_refactoring.agent.signal.SIGTERM,
    ]
    assert process.wait_timeouts == [1.0, 2.0]
    assert process.kill_calls == 0


def test_gracefully_stop_interactive_process_kills_after_signal_timeouts() -> None:
    process = _FakeInteractiveProcess()

    continuous_refactoring.agent._gracefully_stop_interactive_process(
        process,
        interrupt_timeout=1.0,
        terminate_timeout=2.0,
    )

    assert process.signals == [
        continuous_refactoring.agent.signal.SIGINT,
        continuous_refactoring.agent.signal.SIGTERM,
    ]
    assert process.wait_timeouts == [1.0, 2.0, None]
    assert process.kill_calls == 1
    assert process.returncode == -9


def test_run_agent_interactive_until_settled_requests_graceful_exit_after_settle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    content_path = tmp_path / "taste.md"
    settle_path = tmp_path / "taste.md.done"
    pid_path = tmp_path / "pid.txt"
    signal_path = tmp_path / "signal.txt"
    script_path = tmp_path / "writer.py"
    script_path.write_text(
        """
import hashlib
import os
import signal
import sys
import time
from pathlib import Path

content_path = Path(sys.argv[1])
settle_path = Path(sys.argv[2])
pid_path = Path(sys.argv[3])
signal_path = Path(sys.argv[4])
payload = "- settled\\n"

def handle_sigint(_signum, _frame):
    signal_path.write_text("sigint\\n", encoding="utf-8")
    raise SystemExit(0)

signal.signal(signal.SIGINT, handle_sigint)
pid_path.write_text(str(os.getpid()), encoding="utf-8")
content_path.write_text(payload, encoding="utf-8")
settle_path.write_text(
    f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}",
    encoding="utf-8",
)
time.sleep(30)
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr("continuous_refactoring.agent.which", lambda _: "/bin/fake")
    monkeypatch.setattr(
        "continuous_refactoring.agent._build_interactive_command",
        lambda *args, **kwargs: [
            sys.executable,
            str(script_path),
            str(content_path),
            str(settle_path),
            str(pid_path),
            str(signal_path),
        ],
    )

    started = time.monotonic()
    returncode = continuous_refactoring.run_agent_interactive_until_settled(
        "codex",
        "gpt-test",
        "high",
        "prompt",
        tmp_path,
        content_path=content_path,
        settle_path=settle_path,
        settle_window_seconds=0.2,
        poll_interval_seconds=0.05,
    )
    elapsed = time.monotonic() - started

    assert returncode == 0
    assert elapsed < 5
    assert content_path.read_text(encoding="utf-8") == "- settled\n"
    assert signal_path.read_text(encoding="utf-8") == "sigint\n"

    pid = int(pid_path.read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_run_agent_interactive_until_settled_ignores_stale_settle_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    content_path = tmp_path / "taste.md"
    settle_path = tmp_path / "taste.md.done"
    script_path = tmp_path / "writer.py"
    old_payload = "- old\n"
    new_payload = "- new\n"
    content_path.write_text("- old\n", encoding="utf-8")
    settle_path.write_text(
        f"sha256:{hashlib.sha256(old_payload.encode('utf-8')).hexdigest()}",
        encoding="utf-8",
    )
    script_path.write_text(
        """
import hashlib
import sys
import time
from pathlib import Path

content_path = Path(sys.argv[1])
settle_path = Path(sys.argv[2])
payload = "- new\\n"
time.sleep(0.4)
content_path.write_text(payload, encoding="utf-8")
settle_path.write_text(
    f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}",
    encoding="utf-8",
)
time.sleep(30)
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr("continuous_refactoring.agent.which", lambda _: "/bin/fake")
    monkeypatch.setattr(
        "continuous_refactoring.agent._build_interactive_command",
        lambda *args, **kwargs: [
            sys.executable,
            str(script_path),
            str(content_path),
            str(settle_path),
        ],
    )

    started = time.monotonic()
    returncode = continuous_refactoring.run_agent_interactive_until_settled(
        "codex",
        "gpt-test",
        "high",
        "prompt",
        tmp_path,
        content_path=content_path,
        settle_path=settle_path,
        settle_window_seconds=0.2,
        poll_interval_seconds=0.05,
    )
    elapsed = time.monotonic() - started

    assert returncode == 0
    assert elapsed >= 0.5
    assert content_path.read_text(encoding="utf-8") == new_payload


def test_run_agent_interactive_until_settled_restores_terminal_state_and_codex_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    content_path = tmp_path / "taste.md"
    settle_path = tmp_path / "taste.md.done"
    script_path = tmp_path / "writer.py"
    script_path.write_text(
        """
import hashlib
import signal
import sys
import time
from pathlib import Path

content_path = Path(sys.argv[1])
settle_path = Path(sys.argv[2])
payload = "- settled\\n"

def handle_sigint(_signum, _frame):
    raise SystemExit(0)

signal.signal(signal.SIGINT, handle_sigint)
content_path.write_text(payload, encoding="utf-8")
settle_path.write_text(
    f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}",
    encoding="utf-8",
)
time.sleep(30)
""".strip(),
        encoding="utf-8",
    )

    restored: list[tuple[int | None, object | None]] = []
    events: list[str] = []

    monkeypatch.setattr("continuous_refactoring.agent.which", lambda _: "/bin/fake")
    monkeypatch.setattr(
        "continuous_refactoring.agent._build_interactive_command",
        lambda *args, **kwargs: [
            sys.executable,
            str(script_path),
            str(content_path),
            str(settle_path),
        ],
    )
    monkeypatch.setattr("continuous_refactoring.agent._terminal_control_fd", lambda: 99)
    monkeypatch.setattr(
        "continuous_refactoring.agent._capture_terminal_state",
        lambda fd: ["saved-state"] if fd == 99 else None,
    )
    monkeypatch.setattr(
        "continuous_refactoring.agent._restore_terminal_state",
        lambda fd, state: (events.append("restore"), restored.append((fd, state))),
    )
    monkeypatch.setattr(
        "continuous_refactoring.agent._restore_codex_terminal_modes_after_forced_stop",
        lambda: events.append("reset"),
    )
    monkeypatch.setattr(
        "continuous_refactoring.agent._flush_terminal_input",
        lambda fd: events.append(f"flush:{fd}"),
    )

    returncode = continuous_refactoring.run_agent_interactive_until_settled(
        "codex",
        "gpt-test",
        "high",
        "prompt",
        tmp_path,
        content_path=content_path,
        settle_path=settle_path,
        settle_window_seconds=0.2,
        poll_interval_seconds=0.05,
    )

    assert returncode == 0
    assert events == ["reset", "restore", "flush:99"]
    assert restored == [(99, ["saved-state"])]


def test_run_agent_interactive_until_settled_skips_codex_reset_on_clean_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    content_path = tmp_path / "taste.md"
    settle_path = tmp_path / "taste.md.done"
    script_path = tmp_path / "writer.py"
    script_path.write_text(
        """
import hashlib
import sys
from pathlib import Path

content_path = Path(sys.argv[1])
settle_path = Path(sys.argv[2])
payload = "- settled\\n"
content_path.write_text(payload, encoding="utf-8")
settle_path.write_text(
    f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}",
    encoding="utf-8",
)
""".strip(),
        encoding="utf-8",
    )

    codex_resets: list[str] = []
    flushed: list[int | None] = []

    monkeypatch.setattr("continuous_refactoring.agent.which", lambda _: "/bin/fake")
    monkeypatch.setattr(
        "continuous_refactoring.agent._build_interactive_command",
        lambda *args, **kwargs: [
            sys.executable,
            str(script_path),
            str(content_path),
            str(settle_path),
        ],
    )
    monkeypatch.setattr(
        "continuous_refactoring.agent._restore_codex_terminal_modes_after_forced_stop",
        lambda: codex_resets.append("reset"),
    )
    monkeypatch.setattr(
        "continuous_refactoring.agent._flush_terminal_input",
        lambda fd: flushed.append(fd),
    )

    returncode = continuous_refactoring.run_agent_interactive_until_settled(
        "codex",
        "gpt-test",
        "high",
        "prompt",
        tmp_path,
        content_path=content_path,
        settle_path=settle_path,
        settle_window_seconds=0.2,
        poll_interval_seconds=0.05,
    )

    assert returncode == 0
    assert codex_resets == []
    assert flushed == []


def test_restore_codex_terminal_modes_writes_expected_escape_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeTTY:
        def __init__(self) -> None:
            self.buffer = io.BytesIO()

        def isatty(self) -> bool:
            return True

    class FakeNonTTY:
        def isatty(self) -> bool:
            return False

    fake_stdout = FakeTTY()
    monkeypatch.setattr("continuous_refactoring.agent.sys.stdout", fake_stdout)
    monkeypatch.setattr("continuous_refactoring.agent.sys.stderr", FakeNonTTY())

    continuous_refactoring.agent._restore_codex_terminal_modes_after_forced_stop()

    assert fake_stdout.buffer.getvalue() == (
        b"\x1b[<u"
        b"\x1b[?2004l"
        b"\x1b[?1004l"
        b"\x1b[>4m"
        b"\x1b[?25h"
    )


def test_compose_full_prompt_orders_retry_context_then_fix_amendment() -> None:
    target = Target(
        description="foo",
        files=("src/foo.py",),
        scoping=None,
        model_override=None,
        effort_override=None,
    )
    prompt = continuous_refactoring.compose_full_prompt(
        base_prompt="BASE-PROMPT",
        taste="TASTE-TEXT",
        target=target,
        scope_instruction="SCOPE-TEXT",
        validation_command="uv run pytest",
        attempt=2,
        retry_context="RETRY-CONTEXT-OUTPUT",
        fix_amendment="FIX-AMENDMENT-TEXT",
    )

    positions = [
        prompt.index("Attempt 2"),
        prompt.index("BASE-PROMPT"),
        prompt.index(continuous_refactoring.REQUIRED_PREAMBLE),
        prompt.index("TASTE-TEXT"),
        prompt.index("## Target Files"),
        prompt.index("## Scope"),
        prompt.index("## Validation"),
        prompt.index("RETRY-CONTEXT-OUTPUT"),
        prompt.index("FIX-AMENDMENT-TEXT"),
    ]
    assert positions == sorted(positions)


def test_attempt_dir_rejects_retry_below_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmpdir_root))

    artifacts = create_run_artifacts(
        tmp_path,
        agent="codex",
        model="fake-model",
        effort="medium",
        test_command="true",
    )

    with pytest.raises(ValueError, match="retry must be >= 1"):
        artifacts.attempt_dir(1, retry=0)
    with pytest.raises(ValueError, match="retry must be >= 1"):
        artifacts.attempt_dir(1, retry=-1)
    with pytest.raises(ValueError, match="attempt must be >= 1"):
        artifacts.attempt_dir(0)
    with pytest.raises(ValueError, match="attempt must be >= 1"):
        artifacts.attempt_dir(-1)
    # Sanity: retry=1 still works (default path).
    path = artifacts.attempt_dir(1)
    assert path.exists()


def test_create_run_artifacts_uses_single_timestamp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_time = datetime(2026, 4, 15, 12, 34, 56, 123456, tzinfo=timezone.utc)

    class _FrozenDateTime:
        @staticmethod
        def now() -> datetime:
            return fixed_time

    monkeypatch.setattr(artifacts, "datetime", _FrozenDateTime)
    temp_root = tmp_path / "continuous-refactoring-time-test"
    monkeypatch.setattr(artifacts, "default_artifacts_root", lambda: temp_root)
    run = create_run_artifacts(
        temp_root,
        agent="codex",
        model="fake-model",
        effort="medium",
        test_command="true",
    )

    frozen_local = fixed_time.astimezone()
    assert run.run_id == frozen_local.strftime("%Y%m%dT%H%M%S-%f")
    assert run.started_at == fixed_time.astimezone().isoformat(timespec="milliseconds")


def test_default_artifacts_root_prefers_tmpdir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmpdir_root))

    assert artifacts.default_artifacts_root() == tmpdir_root


def test_default_artifacts_root_falls_back_to_tempdir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("TMPDIR", raising=False)
    monkeypatch.setattr(artifacts.tempfile, "gettempdir", lambda: str(tmp_path))

    assert artifacts.default_artifacts_root() == tmp_path


def test_default_artifacts_root_ignores_blank_tmpdir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("TMPDIR", "")
    monkeypatch.setattr(artifacts.tempfile, "gettempdir", lambda: str(tmp_path))

    assert artifacts.default_artifacts_root() == tmp_path


def test_run_summary_write_preserves_previous_content_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = artifacts.RunArtifacts(
        root=tmp_path,
        run_id="run-1",
        repo_root=tmp_path,
        agent="codex",
        model="fake-model",
        effort="medium",
        test_command="true",
        events_path=tmp_path / "events.jsonl",
        summary_path=tmp_path / "summary.json",
        log_path=tmp_path / "run.log",
        started_at="2026-04-15T12:34:56.123+00:00",
    )
    run.summary_path.write_text("previous summary\n", encoding="utf-8")

    def fail_replace(_src: str, _dst: str) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(artifacts.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        run.write_summary()

    assert run.summary_path.read_text(encoding="utf-8") == "previous summary\n"
    assert list(tmp_path.glob("*.tmp")) == []
