from __future__ import annotations

from pathlib import Path

import pytest

import continuous_refactoring
import continuous_refactoring.loop
from continuous_refactoring.artifacts import CommandCapture, ContinuousRefactorError
from continuous_refactoring.decisions import DecisionRecord, RouteOutcome

from conftest import (
    assert_single_prompt,
    failing_tests,
    make_run_once_args,
    noop_agent,
    noop_tests,
    read_single_run_events,
    read_single_run_summary,
    touch_file_agent,
    write_targets_file,
)


def _is_baseline_validation(stdout_path: Path) -> bool:
    parts = stdout_path.parts
    return "baseline" in parts and "initial" in parts


def _planning_record(decision: str) -> DecisionRecord:
    return DecisionRecord(
        decision=decision,  # type: ignore[arg-type]
        retry_recommendation="none" if decision == "commit" else "human-review",
        target="queued-planning",
        call_role="planning.approaches" if decision == "commit" else "planning.state",
        phase_reached="planning.approaches" if decision == "commit" else "planning.state",
        failure_kind="none" if decision == "commit" else "planning-state-missing",
        summary="planning result",
    )


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
    args = make_run_once_args(run_once_env, **kwargs)
    continuous_refactoring.run_once(args)
    assert_single_prompt(prompt_capture, *needles)


def test_run_once_baseline_validation_blocks_routing_and_agent_when_red(
    run_once_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validation_stdout_paths: list[Path] = []

    def fail_validation(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        validation_stdout_paths.append(stdout_path)
        return failing_tests(
            test_command,
            repo_root,
            stdout_path,
            stderr_path,
            **kwargs,
        )

    def trap_route(*_args: object, **_kwargs: object) -> object:
        pytest.fail("run-once must not route work when baseline validation is red")

    def trap_agent(**_kwargs: object) -> CommandCapture:
        pytest.fail("run-once must not invoke the refactor agent when baseline is red")

    monkeypatch.setattr("continuous_refactoring.loop.run_tests", fail_validation)
    monkeypatch.setattr(
        "continuous_refactoring.routing_pipeline.route_and_run",
        trap_route,
    )
    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", trap_agent)

    args = make_run_once_args(run_once_env)
    with pytest.raises(ContinuousRefactorError, match="Baseline validation failed"):
        continuous_refactoring.run_once(args)

    assert len(validation_stdout_paths) == 1
    assert _is_baseline_validation(validation_stdout_paths[0])
    summary = read_single_run_summary(run_once_env)
    assert summary["final_status"] == "baseline_failed"


def test_run_once_runs_baseline_before_refactor_validation(
    run_once_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []

    def tracking_tests(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        if _is_baseline_validation(stdout_path):
            order.append("baseline-validation")
        else:
            order.append("refactor-validation")
        return noop_tests(
            test_command,
            repo_root,
            stdout_path,
            stderr_path,
            **kwargs,
        )

    def tracking_agent(**kwargs: object) -> CommandCapture:
        order.append("agent")
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.run_tests", tracking_tests)
    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", tracking_agent)

    assert continuous_refactoring.run_once(make_run_once_args(run_once_env)) == 0
    assert order == ["baseline-validation", "agent", "refactor-validation"]


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

    validation_calls = 0

    def baseline_passes_then_fails(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        nonlocal validation_calls
        validation_calls += 1
        if _is_baseline_validation(stdout_path):
            return noop_tests(
                test_command,
                repo_root,
                stdout_path,
                stderr_path,
                **kwargs,
            )
        return failing_tests(
            test_command,
            repo_root,
            stdout_path,
            stderr_path,
            **kwargs,
        )

    monkeypatch.setattr(
        "continuous_refactoring.loop.run_tests",
        baseline_passes_then_fails,
    )

    args = make_run_once_args(run_once_env)
    with pytest.raises(ContinuousRefactorError, match="Validation failed after agent"):
        continuous_refactoring.run_once(args)

    assert validation_calls == 2
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

    def baseline_passes_then_fails(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        if _is_baseline_validation(stdout_path):
            return noop_tests(
                test_command,
                repo_root,
                stdout_path,
                stderr_path,
                **kwargs,
            )
        return failing_tests(
            test_command,
            repo_root,
            stdout_path,
            stderr_path,
            **kwargs,
        )

    monkeypatch.setattr(
        "continuous_refactoring.loop.run_tests",
        baseline_passes_then_fails,
    )

    args = make_run_once_args(run_once_env)
    with pytest.raises(ContinuousRefactorError, match="Validation failed after agent"):
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

    targets_file = write_targets_file(
        tmp_path,
        targets=[{
            "description": "direct override",
            "files": ["foo.py"],
            "effort-override": "xhigh",
        }],
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


def test_run_once_commit_message_includes_agent_rationale(
    run_once_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def rationale_agent(**kwargs: object) -> CommandCapture:
        repo_root = Path(str(kwargs.get("repo_root", "")))
        (repo_root / "new_file.txt").write_text("x\n", encoding="utf-8")
        last_message_path = Path(str(kwargs["last_message_path"]))
        last_message_path.parent.mkdir(parents=True, exist_ok=True)
        last_message_path.write_text(
            "\n".join(
                [
                    "BEGIN_CONTINUOUS_REFACTORING_STATUS",
                    "phase_reached: refactor",
                    "decision: commit",
                    "retry_recommendation: none",
                    "failure_kind: none",
                    "summary: Ready to commit.",
                    "commit_rationale: Keep the run-once cleanup reason visible in git history.",
                    "next_retry_focus: none",
                    "tests_run: uv run pytest",
                    "evidence:",
                    "  - tests.stdout.log",
                    "END_CONTINUOUS_REFACTORING_STATUS",
                ],
            ),
            encoding="utf-8",
        )
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", rationale_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    exit_code = continuous_refactoring.run_once(
        make_run_once_args(run_once_env, validation_command="uv run pytest"),
    )

    assert exit_code == 0
    message = continuous_refactoring.run_command(
        ["git", "log", "-1", "--format=%B"], cwd=run_once_env,
    ).stdout
    assert "Why:\nKeep the run-once cleanup reason visible in git history." in message
    assert "Validation:\nuv run pytest" in message


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


def test_run_once_resumes_planning_before_classification(
    run_once_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = run_once_env / ".migrations"
    live_dir.mkdir()
    monkeypatch.setattr(
        "continuous_refactoring.loop._resolve_live_migrations_dir",
        lambda _repo_root: live_dir,
    )
    planning_calls = 0

    def fake_planning_tick(
        live_dir: Path,
        taste: str,
        repo_root: Path,
        artifacts: object,
        **kwargs: object,
    ) -> tuple[RouteOutcome, DecisionRecord | None]:
        nonlocal planning_calls
        planning_calls += 1
        (repo_root / "planning-step.txt").write_text("planned\n", encoding="utf-8")
        head_before = continuous_refactoring.run_command(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
        ).stdout.strip()
        kwargs["finalize_commit"](
            repo_root,
            head_before,
            "continuous refactor: planning/queued-planning/approaches\n"
            "\n"
            "Why:\n"
            "planning result",
            artifacts=artifacts,
            attempt=kwargs["attempt"],
            phase="planning",
        )
        return ("commit", _planning_record("commit"))

    monkeypatch.setattr(
        "continuous_refactoring.routing_pipeline._try_planning_tick",
        fake_planning_tick,
    )
    monkeypatch.setattr(
        "continuous_refactoring.routing_pipeline.classify_target",
        lambda *_args, **_kwargs: pytest.fail("classification must wait for planning"),
    )

    assert continuous_refactoring.run_once(make_run_once_args(run_once_env)) == 0
    assert planning_calls == 1


def test_run_once_raises_when_planning_resume_blocks(
    run_once_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = run_once_env / ".migrations"
    live_dir.mkdir()
    monkeypatch.setattr(
        "continuous_refactoring.loop._resolve_live_migrations_dir",
        lambda _repo_root: live_dir,
    )
    monkeypatch.setattr(
        "continuous_refactoring.routing_pipeline._try_planning_tick",
        lambda *_args, **_kwargs: ("blocked", _planning_record("blocked")),
    )
    monkeypatch.setattr(
        "continuous_refactoring.routing_pipeline.classify_target",
        lambda *_args, **_kwargs: pytest.fail("blocked planning must not classify"),
    )

    with pytest.raises(ContinuousRefactorError, match="planning result"):
        continuous_refactoring.run_once(make_run_once_args(run_once_env))
