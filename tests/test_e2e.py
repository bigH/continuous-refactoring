from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

import continuous_refactoring
import continuous_refactoring.loop
from continuous_refactoring.artifacts import CommandCapture
from continuous_refactoring.config import default_taste_text, register_project

from conftest import make_run_once_args, noop_agent, noop_tests, write_fake_codex


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _read_single_run_summary(tmp_path: Path) -> dict[str, object]:
    run_root = tmp_path / "tmpdir" / "continuous-refactoring"
    run_dirs = list(run_root.iterdir())
    assert len(run_dirs) == 1
    summary_path = run_dirs[0] / "summary.json"
    assert summary_path.exists()
    return json.loads(summary_path.read_text(encoding="utf-8"))


def _assert_final_status(tmp_path: Path, expected_status: str) -> None:
    summary = _read_single_run_summary(tmp_path)
    assert summary["final_status"] == expected_status


def _assert_single_prompt(prompt_capture: list[str], *needles: str) -> None:
    assert len(prompt_capture) == 1
    prompt = prompt_capture[0]
    for needle in needles:
        assert needle in prompt


def test_e2e_init_then_run_once(
    run_once_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full flow: init project, run-once with fake agent, verify branch/commit/summary."""
    bin_dir = tmp_path / "bin"
    write_fake_codex(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_CODEX_STDOUT", "chosen_scope: e2e cleanup\n")
    monkeypatch.setenv("FAKE_CODEX_LAST_MESSAGE", "chosen_scope: e2e cleanup\n")
    monkeypatch.setenv("FAKE_CODEX_TOUCH_FILE", "e2e_file.txt")
    monkeypatch.setenv("FAKE_CODEX_TOUCH_CONTENT", "e2e content\n")

    register_project(run_once_env)

    args = make_run_once_args(run_once_env)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0

    branch = continuous_refactoring.current_branch(run_once_env)
    assert branch.startswith("cr/")

    log_output = subprocess.run(
        ["git", "log", "--oneline"], cwd=run_once_env,
        capture_output=True, text=True, check=True,
    ).stdout
    assert "continuous refactor" in log_output

    _assert_final_status(tmp_path, "completed")


def test_e2e_init_then_run_with_failures(
    run_once_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run loop with two targets: first fails validation, second succeeds."""
    register_project(run_once_env)

    call_count = 0

    def alternating_agent(**kwargs: object) -> CommandCapture:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            rr = Path(str(kwargs.get("repo_root", "")))
            (rr / "good_change.txt").write_text("good\n", encoding="utf-8")
        return noop_agent(**kwargs)

    test_call_count = 0

    def baseline_then_alternate(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        nonlocal test_call_count
        test_call_count += 1
        # Call 1: baseline check (pass)
        # Call 2: first target validation (fail)
        # Call 3: second target validation (pass)
        if test_call_count == 2:
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            stdout_path.write_text("FAILED\n", encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")
            return CommandCapture(
                command=("pytest",),
                returncode=1,
                stdout="FAILED\n",
                stderr="",
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
        return noop_tests(test_command, repo_root, stdout_path, stderr_path)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", alternating_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", baseline_then_alternate)

    targets_file = tmp_path / "targets.jsonl"
    targets_file.write_text(
        json.dumps({"description": "target-1", "files": ["a.py"]}) + "\n"
        + json.dumps({"description": "target-2", "files": ["b.py"]}) + "\n",
        encoding="utf-8",
    )

    args = argparse.Namespace(
        agent="codex",
        model="fake-model",
        effort="xhigh",
        validation_command=f"{sys.executable} -c \"print('ok')\"",
        extensions=None,
        globs=None,
        targets=targets_file,
        paths=None,
        scope_instruction=None,
        timeout=None,
        refactoring_prompt=None,
        fix_prompt=None,
        show_agent_logs=False,
        show_command_logs=False,
        repo_root=run_once_env,
        max_attempts=None,
        max_refactors=None,
        no_push=True,
        push_remote="origin",
        commit_message_prefix="continuous refactor",
        max_consecutive_failures=5,
        use_branch=None,
    )
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    # First target failed validation, second succeeded with changes
    log_output = subprocess.run(
        ["git", "log", "--oneline"], cwd=run_once_env,
        capture_output=True, text=True, check=True,
    ).stdout
    assert "target-2" in log_output
    assert "target-1" not in log_output


def test_e2e_taste_flows_through(
    run_once_env: Path,
    prompt_capture: list[str],
) -> None:
    """Custom taste text appears in the agent prompt."""
    project = register_project(run_once_env)
    custom_taste = "- Never use print statements in production code.\n"
    (project.project_dir / "taste.md").write_text(custom_taste, encoding="utf-8")

    args = make_run_once_args(run_once_env)
    continuous_refactoring.run_once(args)

    _assert_single_prompt(prompt_capture, "Never use print statements in production code")


def test_e2e_targets_jsonl_flow(
    run_once_env: Path,
    tmp_path: Path,
    prompt_capture: list[str],
) -> None:
    """Targets from JSONL file appear in agent prompt."""
    register_project(run_once_env)

    targets_file = tmp_path / "targets.jsonl"
    targets_file.write_text(
        json.dumps({
            "description": "clean up error handling",
            "files": ["src/errors.py", "src/handlers.py"],
            "scoping": "focus on exception translation",
        }) + "\n",
        encoding="utf-8",
    )

    args = make_run_once_args(run_once_env, targets=targets_file, scope_instruction=None)
    continuous_refactoring.run_once(args)

    _assert_single_prompt(
        prompt_capture,
        "src/errors.py",
        "src/handlers.py",
        "focus on exception translation",
    )


def test_e2e_ctrl_c_cleanup(
    run_once_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Interrupt mid-run produces exit code 130 and artifact logs mention interruption."""
    register_project(run_once_env)

    def interrupting_agent(**kwargs: object) -> CommandCapture:
        raise KeyboardInterrupt

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", interrupting_agent)

    args = make_run_once_args(run_once_env)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 130

    captured = capsys.readouterr()
    assert "Artifact logs:" in captured.err

    _assert_final_status(tmp_path, "interrupted")


def test_e2e_without_init_uses_default_taste(
    run_once_env: Path,
    prompt_capture: list[str],
) -> None:
    """Without init, run succeeds and the built-in default taste text appears in the prompt."""
    # No register_project call

    args = make_run_once_args(run_once_env)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0

    _assert_single_prompt(prompt_capture)
    builtin_taste = default_taste_text()
    for line in builtin_taste.splitlines():
        line = line.strip()
        if line.startswith("-"):
            _assert_single_prompt(prompt_capture, line.lstrip("- "))
