from __future__ import annotations

import hashlib
import os
import re
import sys
import time
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


def test_build_command_claude_streams_json_so_watchdog_sees_progress() -> None:
    command = continuous_refactoring.build_command(
        "claude", "opus", "medium", "do the thing", Path("/repo"),
    )

    assert command[:2] == ["claude", "--print"]
    assert "--verbose" in command
    assert "--include-partial-messages" in command
    fmt_index = command.index("--output-format")
    assert command[fmt_index + 1] == "stream-json"


def test_run_agent_interactive_until_settled_kills_process_after_settle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    content_path = tmp_path / "taste.md"
    settle_path = tmp_path / "taste.md.done"
    pid_path = tmp_path / "pid.txt"
    script_path = tmp_path / "writer.py"
    script_path.write_text(
        """
import hashlib
import os
import sys
import time
from pathlib import Path

content_path = Path(sys.argv[1])
settle_path = Path(sys.argv[2])
pid_path = Path(sys.argv[3])
payload = "- settled\\n"
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
