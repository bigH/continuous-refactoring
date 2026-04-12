from __future__ import annotations

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


def test_build_claude_command_streams_json_so_watchdog_sees_progress() -> None:
    command = continuous_refactoring.build_claude_command(
        "opus", "medium", "do the thing", Path("/repo"),
    )

    assert command[:2] == ["claude", "--print"]
    assert "--verbose" in command
    assert "--include-partial-messages" in command
    fmt_index = command.index("--output-format")
    assert command[fmt_index + 1] == "stream-json"


