from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import continuous_refactoring


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


def test_extract_chosen_target_accepts_chosen_scope() -> None:
    text = """
    chosen_scope:
    - compiler cleanup batch
    """

    assert (
        continuous_refactoring.extract_chosen_target(text)
        == "compiler cleanup batch"
    )


def test_build_claude_command_streams_json_so_watchdog_sees_progress() -> None:
    command = continuous_refactoring.build_claude_command(
        "opus", "medium", "do the thing", Path("/repo"),
    )

    assert command[:2] == ["claude", "--print"]
    assert "--verbose" in command
    assert "--include-partial-messages" in command
    fmt_index = command.index("--output-format")
    assert command[fmt_index + 1] == "stream-json"


def test_extract_stream_json_text_prefers_result_event() -> None:
    stdout = "\n".join([
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "thinking..."}]},
        }),
        json.dumps({"type": "result", "subtype": "success", "result": "final text"}),
    ])

    assert continuous_refactoring.extract_stream_json_text(stdout) == "final text"


def test_extract_stream_json_text_falls_back_to_assistant_text() -> None:
    stdout = "\n".join([
        json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "first"}]},
        }),
        json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "second"}]},
        }),
    ])

    assert continuous_refactoring.extract_stream_json_text(stdout) == "first\nsecond"


def test_extract_stream_json_text_returns_none_for_plain_text() -> None:
    assert continuous_refactoring.extract_stream_json_text("just a text blob") is None


def test_resolve_phase_target_reads_stream_json_result(tmp_path: Path) -> None:
    stdout = json.dumps({
        "type": "result",
        "subtype": "success",
        "result": "chosen_scope: dedupe the widget cache",
    })
    capture = continuous_refactoring.CommandCapture(
        command=("claude", "--print"),
        returncode=0,
        stdout=stdout,
        stderr="",
        stdout_path=tmp_path / "out.log",
        stderr_path=tmp_path / "err.log",
    )

    assert (
        continuous_refactoring.resolve_phase_target(capture, None)
        == "dedupe the widget cache"
    )
