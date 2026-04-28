from __future__ import annotations

import json
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
    read_single_run_events,
    read_single_run_summary,
    touch_file_agent,
)


def _run_once_prompt_capture(
    run_once_env: Path, prompt_capture: list[str], **kwargs: object
) -> str:
    args = make_run_once_args(run_once_env, **kwargs)
    continuous_refactoring.run_once(args)
    assert len(prompt_capture) == 1
    return prompt_capture[0]


@pytest.mark.parametrize(
    ("kwargs", "needles"),
    [
        ({}, ("## Refactoring Taste",)),
        (
            {"paths": "src/foo.py:src/bar.py"},
            ("## Target Files", "src/foo.py", "src/bar.py"),
        ),
        (
            {"scope_instruction": "focus on error handling"},
            ("## Scope", "focus on error handling"),
        ),
    ],
)
def test_run_once_prompt_composition(
    run_once_env: Path,
    prompt_capture: list[str],
    kwargs: dict[str, object],
    needles: tuple[str, ...],
) -> None:
    prompt = _run_once_prompt_capture(run_once_env, prompt_capture, **kwargs)
    for needle in needles:
        assert needle in prompt


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


def test_run_once_agent_failure_undoes_commits(
    run_once_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def commit_twice_then_fail(**kwargs: object) -> CommandCapture:
        rr = Path(str(kwargs.get("repo_root", "")))
        stdout_path = Path(str(kwargs["stdout_path"]))
        stderr_path = Path(str(kwargs["stderr_path"]))
        for name in ("bad", "worse"):
            (rr / f"{name}_change.txt").write_text(f"{name}\n", encoding="utf-8")
            continuous_refactoring.run_command(["git", "add", "-A"], cwd=rr)
            continuous_refactoring.run_command(
                ["git", "commit", "-m", f"agent {name} commit"],
                cwd=rr,
            )
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text("fail\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return CommandCapture(
            command=("fake",),
            returncode=1,
            stdout="fail\n",
            stderr="",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )

    monkeypatch.setattr(
        "continuous_refactoring.loop.maybe_run_agent",
        commit_twice_then_fail,
    )

    args = make_run_once_args(run_once_env)
    with pytest.raises(ContinuousRefactorError, match="Agent failed"):
        continuous_refactoring.run_once(args)

    log = continuous_refactoring.run_command(
        ["git", "log", "--oneline"], cwd=run_once_env,
    )
    assert "agent bad commit" not in log.stdout
    assert "agent worse commit" not in log.stdout
    status = continuous_refactoring.run_command(
        ["git", "status", "--porcelain"], cwd=run_once_env,
    )
    assert status.stdout == ""


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


def test_run_once_direct_refactor_audits_effort_budget(
    run_once_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_efforts: list[str] = []

    def effort_capturing_agent(**kwargs: object) -> CommandCapture:
        captured_efforts.append(str(kwargs.get("effort", "")))
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", effort_capturing_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    targets_file = tmp_path / "targets.jsonl"
    targets_file.write_text(
        json.dumps({
            "description": "direct override",
            "files": ["foo.py"],
            "effort-override": "xhigh",
        }),
        encoding="utf-8",
    )
    args = make_run_once_args(
        run_once_env,
        targets=targets_file,
        scope_instruction=None,
        default_effort="low",
        max_allowed_effort="medium",
    )

    assert continuous_refactoring.run_once(args) == 0
    assert captured_efforts == ["medium"]

    summary = read_single_run_summary(run_once_env)
    attempt = summary["attempts"][0]
    assert attempt["requested_effort"] == "xhigh"
    assert attempt["effective_effort"] == "medium"
    assert attempt["max_allowed_effort"] == "medium"
    assert attempt["effort_source"] == "target-override"
    assert attempt["effort_capped"] is True

    refactor_events = [
        event for event in read_single_run_events(run_once_env)
        if event.get("event") == "call_started"
        and event.get("call_role") == "refactor"
    ]
    assert refactor_events
    assert refactor_events[0]["requested_effort"] == "xhigh"
    assert refactor_events[0]["effective_effort"] == "medium"


def test_run_once_prints_diff(
    run_once_env: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "continuous_refactoring.loop.maybe_run_agent",
        touch_file_agent("new_file.txt"),
    )
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    exit_code = continuous_refactoring.run_once(make_run_once_args(run_once_env))

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Branch:" not in output
    assert "new_file.txt" in output


def test_run_once_prints_and_records_commit(
    run_once_env: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "continuous_refactoring.loop.maybe_run_agent",
        touch_file_agent("new_file.txt"),
    )
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    exit_code = continuous_refactoring.run_once(make_run_once_args(run_once_env))

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Committed: " in output

    log = continuous_refactoring.run_command(
        ["git", "log", "--oneline"], cwd=run_once_env,
    ).stdout
    assert "continuous refactor: run-once" in log

    summary = read_single_run_summary(run_once_env)
    assert summary["counts"]["commits_created"] == 1
    attempts = summary["attempts"]
    assert len(attempts) == 1
    assert attempts[0]["commit_phase"] == "run_once"


def test_run_once_replaces_agent_commit_with_driver_commit(
    run_once_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def committing_agent(**kwargs: object) -> CommandCapture:
        rr = Path(str(kwargs.get("repo_root", "")))
        (rr / "agent_change.txt").write_text("x\n", encoding="utf-8")
        continuous_refactoring.run_command(["git", "add", "-A"], cwd=rr)
        continuous_refactoring.run_command(
            ["git", "commit", "-m", "agent commit"], cwd=rr,
        )
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", committing_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    exit_code = continuous_refactoring.run_once(make_run_once_args(run_once_env))

    assert exit_code == 0
    log = continuous_refactoring.run_command(
        ["git", "log", "--oneline"], cwd=run_once_env,
    ).stdout
    assert "continuous refactor: run-once" in log
    assert "agent commit" not in log

    summary = read_single_run_summary(run_once_env)
    attempt = summary["attempts"][0]
    assert attempt["commit_phase"] == "run_once"


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
