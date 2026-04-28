from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

import continuous_refactoring
import continuous_refactoring.loop
from continuous_refactoring.artifacts import CommandCapture
from continuous_refactoring.config import default_taste_text, register_project

from conftest import (
    assert_single_prompt,
    assert_single_run_final_status,
    make_run_loop_args,
    make_run_once_args,
    noop_agent,
    noop_tests,
    write_fake_codex,
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

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
    starting_branch = continuous_refactoring.current_branch(run_once_env)

    args = make_run_once_args(run_once_env)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0
    assert continuous_refactoring.current_branch(run_once_env) == starting_branch

    log_output = subprocess.run(
        ["git", "log", "--oneline"], cwd=run_once_env,
        capture_output=True, text=True, check=True,
    ).stdout
    assert "continuous refactor" in log_output

    assert_single_run_final_status(run_once_env, "completed")


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

    args = make_run_loop_args(
        run_once_env,
        targets=targets_file,
        scope_instruction=None,
        max_consecutive_failures=5,
    )
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    # Targets run in random order: one fails validation, the other commits.
    log_output = subprocess.run(
        ["git", "log", "--oneline"], cwd=run_once_env,
        capture_output=True, text=True, check=True,
    ).stdout
    assert ("target-1" in log_output) ^ ("target-2" in log_output)


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

    assert_single_prompt(prompt_capture, "Never use print statements in production code")


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

    assert_single_prompt(
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

    assert_single_run_final_status(run_once_env, "interrupted")


def test_e2e_without_init_uses_default_taste(
    run_once_env: Path,
    prompt_capture: list[str],
) -> None:
    """Without init, run succeeds and the built-in default taste text appears in the prompt."""
    # No register_project call

    args = make_run_once_args(run_once_env)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0

    needles = [
        line.strip().lstrip("- ")
        for line in default_taste_text().splitlines()
        if line.strip().startswith("-")
    ]
    assert_single_prompt(prompt_capture, *needles)
