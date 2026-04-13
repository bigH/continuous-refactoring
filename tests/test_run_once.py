from __future__ import annotations

import re
from pathlib import Path

import pytest

import continuous_refactoring
import continuous_refactoring.loop
from continuous_refactoring.artifacts import CommandCapture, ContinuousRefactorError

from conftest import (
    failing_tests,
    make_run_once_args,
    noop_agent,
    noop_tests,
)


def test_run_once_creates_branch(
    run_once_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", noop_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    args = make_run_once_args(run_once_env)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0
    branch = continuous_refactoring.current_branch(run_once_env)
    assert re.match(r"^cr/\d{8}T\d{6}$", branch)


def test_run_once_composes_prompt_with_taste(
    run_once_env: Path,
    prompt_capture: list[str],
) -> None:
    args = make_run_once_args(run_once_env)
    continuous_refactoring.run_once(args)

    assert len(prompt_capture) == 1
    assert "## Refactoring Taste" in prompt_capture[0]


def test_run_once_composes_prompt_with_target(
    run_once_env: Path,
    prompt_capture: list[str],
) -> None:
    args = make_run_once_args(run_once_env, paths="src/foo.py:src/bar.py")
    continuous_refactoring.run_once(args)

    assert len(prompt_capture) == 1
    assert "## Target Files" in prompt_capture[0]
    assert "src/foo.py" in prompt_capture[0]
    assert "src/bar.py" in prompt_capture[0]


def test_run_once_composes_prompt_with_scope(
    run_once_env: Path,
    prompt_capture: list[str],
) -> None:
    args = make_run_once_args(run_once_env, scope_instruction="focus on error handling")
    continuous_refactoring.run_once(args)

    assert len(prompt_capture) == 1
    assert "## Scope" in prompt_capture[0]
    assert "focus on error handling" in prompt_capture[0]


def test_run_once_validation_gate(
    run_once_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def committing_agent(**kwargs: object) -> CommandCapture:
        rr = Path(str(kwargs.get("repo_root", "")))
        (rr / "new_file.txt").write_text("agent wrote this\n", encoding="utf-8")
        continuous_refactoring.run_command(["git", "add", "-A"], cwd=rr)
        continuous_refactoring.run_command(
            ["git", "commit", "-m", "agent commit"], cwd=rr,
        )
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", committing_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", failing_tests)

    args = make_run_once_args(run_once_env)
    with pytest.raises(ContinuousRefactorError, match="Validation failed"):
        continuous_refactoring.run_once(args)

    log = continuous_refactoring.run_command(
        ["git", "log", "--oneline"], cwd=run_once_env,
    )
    assert "agent commit" not in log.stdout


def test_run_once_no_fix_retry(
    run_once_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent_call_count = 0

    def counting_agent(**kwargs: object) -> CommandCapture:
        nonlocal agent_call_count
        agent_call_count += 1
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", counting_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", failing_tests)

    args = make_run_once_args(run_once_env)
    with pytest.raises(ContinuousRefactorError, match="Validation failed"):
        continuous_refactoring.run_once(args)

    assert agent_call_count == 1


def test_run_once_prints_branch_and_diff(
    run_once_env: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", noop_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    args = make_run_once_args(run_once_env)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Branch: cr/" in output


def test_run_once_timeout(
    run_once_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout_agent(**kwargs: object) -> CommandCapture:
        raise ContinuousRefactorError("Command timed out after 1s: fake")

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", timeout_agent)

    args = make_run_once_args(run_once_env, timeout=1)
    with pytest.raises(ContinuousRefactorError, match="timed out"):
        continuous_refactoring.run_once(args)


def test_run_once_uses_default_prompt(
    run_once_env: Path,
    prompt_capture: list[str],
) -> None:
    args = make_run_once_args(run_once_env)
    continuous_refactoring.run_once(args)

    assert len(prompt_capture) == 1
    assert "You are a continuous refactoring agent" in prompt_capture[0]


def test_ctrl_c_prints_file_paths(
    run_once_env: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def interrupting_agent(**kwargs: object) -> CommandCapture:
        raise KeyboardInterrupt

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", interrupting_agent)

    args = make_run_once_args(run_once_env)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 130
    captured = capsys.readouterr()
    assert "Artifact logs:" in captured.err


def test_run_once_use_branch_creates_when_absent(
    run_once_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", noop_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    args = make_run_once_args(run_once_env, use_branch="my-cleanup")
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0
    assert continuous_refactoring.current_branch(run_once_env) == "my-cleanup"


def test_run_once_use_branch_reuses_existing(
    run_once_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    continuous_refactoring.run_command(
        ["git", "checkout", "-b", "my-cleanup"], cwd=run_once_env,
    )
    (run_once_env / "marker.txt").write_text("marker\n", encoding="utf-8")
    continuous_refactoring.run_command(["git", "add", "marker.txt"], cwd=run_once_env)
    continuous_refactoring.run_command(
        ["git", "commit", "-m", "marker commit"], cwd=run_once_env,
    )
    expected_head = continuous_refactoring.run_command(
        ["git", "rev-parse", "HEAD"], cwd=run_once_env,
    ).stdout.strip()
    continuous_refactoring.run_command(["git", "checkout", "main"], cwd=run_once_env)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", noop_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    args = make_run_once_args(run_once_env, use_branch="my-cleanup")
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0
    assert continuous_refactoring.current_branch(run_once_env) == "my-cleanup"
    log = continuous_refactoring.run_command(
        ["git", "log", "--oneline"], cwd=run_once_env,
    ).stdout
    assert "marker commit" in log
    current_head = continuous_refactoring.run_command(
        ["git", "rev-parse", "HEAD"], cwd=run_once_env,
    ).stdout.strip()
    assert current_head == expected_head
