from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

import continuous_refactoring
from continuous_refactoring.artifacts import create_run_artifacts
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


def test_build_claude_command_streams_json_so_watchdog_sees_progress() -> None:
    command = continuous_refactoring.build_claude_command(
        "opus", "medium", "do the thing", Path("/repo"),
    )

    assert command[:2] == ["claude", "--print"]
    assert "--verbose" in command
    assert "--include-partial-messages" in command
    fmt_index = command.index("--output-format")
    assert command[fmt_index + 1] == "stream-json"


def test_compose_full_prompt_orders_previous_failure_then_fix_amendment() -> None:
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
        previous_failure="PREV-FAIL-OUTPUT",
        fix_amendment="FIX-AMENDMENT-TEXT",
    )

    positions = {
        "attempt": prompt.index("Attempt 2"),
        "base": prompt.index("BASE-PROMPT"),
        "preamble": prompt.index(continuous_refactoring.REQUIRED_PREAMBLE),
        "taste": prompt.index("TASTE-TEXT"),
        "files": prompt.index("## Target Files"),
        "scope": prompt.index("## Scope"),
        "validation": prompt.index("## Validation"),
        "previous": prompt.index("PREV-FAIL-OUTPUT"),
        "amendment": prompt.index("FIX-AMENDMENT-TEXT"),
    }
    ordered = [
        positions["attempt"],
        positions["base"],
        positions["preamble"],
        positions["taste"],
        positions["files"],
        positions["scope"],
        positions["validation"],
        positions["previous"],
        positions["amendment"],
    ]
    assert ordered == sorted(ordered)


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
    # Sanity: retry=1 still works (default path).
    path = artifacts.attempt_dir(1)
    assert path.exists()

