from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import continuous_refactoring
import continuous_refactoring.loop
from continuous_refactoring.cli import build_parser
from continuous_refactoring.artifacts import CommandCapture, ContinuousRefactorError
from continuous_refactoring.migrations import MigrationManifest, PhaseSpec, save_manifest

from conftest import (
    failing_tests,
    init_repo,
    make_run_loop_args,
    noop_agent,
    noop_tests,
)


def _read_single_run_summary(repo_root: Path) -> dict[str, object]:
    run_root = repo_root.parent / "tmpdir" / "continuous-refactoring"
    run_dirs = list(run_root.iterdir())
    assert len(run_dirs) == 1
    return json.loads((run_dirs[0] / "summary.json").read_text(encoding="utf-8"))


def _read_single_run_events(repo_root: Path) -> list[dict[str, object]]:
    run_root = repo_root.parent / "tmpdir" / "continuous-refactoring"
    run_dirs = list(run_root.iterdir())
    assert len(run_dirs) == 1
    return [
        json.loads(line)
        for line in (run_dirs[0] / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_live_manifest(
    live_dir: Path,
    *,
    name: str = "queued-migration",
    status: str = "ready",
) -> None:
    manifest = MigrationManifest(
        name=name,
        created_at="2026-04-16T00:00:00.000+00:00",
        last_touch="2026-04-16T00:00:00.000+00:00",
        wake_up_on=None,
        awaiting_human_review=False,
        status=status,
        current_phase=0,
        phases=(
            PhaseSpec(
                name="cleanup",
                file="phase-0-cleanup.md",
                done=False,
                ready_when="always",
            ),
        ),
    )
    migration_dir = live_dir / name
    migration_dir.mkdir(parents=True, exist_ok=True)
    save_manifest(manifest, migration_dir / "manifest.json")


def _failing_agent(**kwargs: object) -> CommandCapture:
    stdout_path = kwargs.get("stdout_path")
    stderr_path = kwargs.get("stderr_path")
    if stdout_path:
        Path(stdout_path).parent.mkdir(parents=True, exist_ok=True)
        Path(stdout_path).write_text("fail\n", encoding="utf-8")
    if stderr_path:
        Path(stderr_path).parent.mkdir(parents=True, exist_ok=True)
        Path(stderr_path).write_text("", encoding="utf-8")
    return CommandCapture(
        command=("fake",),
        returncode=1,
        stdout="fail\n",
        stderr="",
        stdout_path=Path(stdout_path) if stdout_path else Path("/dev/null"),
        stderr_path=Path(stderr_path) if stderr_path else Path("/dev/null"),
    )


def test_run_parser_accepts_sleep_flag() -> None:
    args = build_parser().parse_args(
        [
            "run",
            "--with", "codex",
            "--model", "m",
            "--effort", "high",
            "--scope-instruction", "s",
            "--max-refactors", "1",
            "--sleep", "0.25",
        ],
    )

    assert args.sleep == 0.25


def test_run_commits_after_successful_change(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env

    def touching_agent(**kwargs: object) -> CommandCapture:
        rr = Path(str(kwargs.get("repo_root", "")))
        (rr / "touched.txt").write_text("touched\n", encoding="utf-8")
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", touching_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    args = make_run_loop_args(repo_root, max_refactors=1)
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    log = continuous_refactoring.run_command(
        ["git", "log", "--oneline"], cwd=repo_root,
    ).stdout
    assert "continuous refactor: random files" in log


def test_run_sleeps_only_between_targets(
    run_loop_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env
    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", noop_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    sleep_calls: list[float] = []
    monkeypatch.setattr("continuous_refactoring.loop.time.sleep", sleep_calls.append)

    targets_file = tmp_path / "targets.jsonl"
    targets_file.write_text(
        "\n".join(
            json.dumps({"description": f"target-{index}", "files": [f"file{index}.py"]})
            for index in range(3)
        ),
        encoding="utf-8",
    )

    args = make_run_loop_args(
        repo_root,
        targets=targets_file,
        scope_instruction=None,
        sleep=0.25,
    )
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    assert sleep_calls == [0.25, 0.25]


def test_run_summary_has_no_publish_fields(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env

    def touching_agent(**kwargs: object) -> CommandCapture:
        rr = Path(str(kwargs.get("repo_root", "")))
        (rr / "touched.txt").write_text("touched\n", encoding="utf-8")
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", touching_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    args = make_run_loop_args(repo_root, max_refactors=1)
    exit_code = continuous_refactoring.run_loop(args)

    summary = _read_single_run_summary(repo_root)

    assert exit_code == 0
    assert set(summary["counts"]) == {"attempts_started", "commits_created"}
    assert set(summary["attempts"][0]) >= {
        "attempt",
        "call_role",
        "commit_phase",
        "commit_sha",
        "decision",
        "failure_kind",
        "failure_summary",
        "phase_reached",
        "reason_doc_path",
        "retry",
        "retry_recommendation",
        "target",
    }


def test_run_does_not_sleep_between_retries(
    run_loop_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env

    agent_calls = 0

    def touching_agent(**kwargs: object) -> CommandCapture:
        nonlocal agent_calls
        agent_calls += 1
        rr = Path(str(kwargs.get("repo_root", "")))
        (rr / f"touched-{agent_calls}.txt").write_text("x\n", encoding="utf-8")
        return noop_agent(**kwargs)

    validation_calls = 0

    def fail_first_attempt_then_pass(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        nonlocal validation_calls
        if not _count_validation_calls(stdout_path):
            return noop_tests(test_command, repo_root, stdout_path, stderr_path)
        validation_calls += 1
        if validation_calls == 1:
            return failing_tests(test_command, repo_root, stdout_path, stderr_path)
        return noop_tests(test_command, repo_root, stdout_path, stderr_path)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", touching_agent)
    monkeypatch.setattr(
        "continuous_refactoring.loop.run_tests", fail_first_attempt_then_pass,
    )

    sleep_calls: list[float] = []
    monkeypatch.setattr("continuous_refactoring.loop.time.sleep", sleep_calls.append)

    targets_file = tmp_path / "targets.jsonl"
    targets_file.write_text(
        "\n".join(
            json.dumps({"description": f"target-{index}", "files": [f"file{index}.py"]})
            for index in range(2)
        ),
        encoding="utf-8",
    )

    args = make_run_loop_args(
        repo_root,
        targets=targets_file,
        scope_instruction=None,
        sleep=0.4,
        max_attempts=3,
    )
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    assert agent_calls == 3
    assert validation_calls == 3
    assert sleep_calls == [0.4]


def test_run_reports_and_records_driver_owned_commit_for_agent_commit(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = run_loop_env

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

    exit_code = continuous_refactoring.run_loop(make_run_loop_args(repo_root, max_refactors=1))

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Committed: " in output

    log = continuous_refactoring.run_command(
        ["git", "log", "--oneline"], cwd=repo_root,
    ).stdout
    assert "continuous refactor: random files" in log
    assert "agent commit" not in log

    summary = _read_single_run_summary(repo_root)
    assert summary["counts"]["commits_created"] == 1
    attempts = summary["attempts"]
    assert len(attempts) == 1
    assert attempts[0]["commit_phase"] == "refactor"


def test_run_routed_planning_reports_and_records_commit(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = run_loop_env
    live_dir = repo_root / ".migrations"
    live_dir.mkdir()
    monkeypatch.setattr(
        "continuous_refactoring.loop._resolve_live_migrations_dir",
        lambda _repo_root: live_dir,
    )
    monkeypatch.setattr(
        "continuous_refactoring.loop.classify_target",
        lambda *_args, **_kwargs: "needs-plan",
    )

    class StubPlanningOutcome:
        status = "ready"
        reason = "stub"

    def fake_run_planning(*_args: object, **_kwargs: object) -> StubPlanningOutcome:
        (repo_root / "plan.txt").write_text("plan\n", encoding="utf-8")
        return StubPlanningOutcome()

    monkeypatch.setattr("continuous_refactoring.loop.run_planning", fake_run_planning)

    exit_code = continuous_refactoring.run_loop(make_run_loop_args(repo_root, max_refactors=1))

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Classification: needs-plan — random files" in output
    assert "Committed: " in output
    assert "Planning: queued for execution — stub" in output

    log = continuous_refactoring.run_command(
        ["git", "log", "--oneline"], cwd=repo_root,
    ).stdout
    assert "continuous refactor: plan " in log


def test_run_routed_planning_surfaces_human_review_requirement(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = run_loop_env
    live_dir = repo_root / ".migrations"
    live_dir.mkdir()
    monkeypatch.setattr(
        "continuous_refactoring.loop._resolve_live_migrations_dir",
        lambda _repo_root: live_dir,
    )
    monkeypatch.setattr(
        "continuous_refactoring.loop.classify_target",
        lambda *_args, **_kwargs: "needs-plan",
    )

    class StubPlanningOutcome:
        status = "awaiting_human_review"
        reason = "phase 2 has a decision gap"

    def fake_run_planning(*_args: object, **_kwargs: object) -> StubPlanningOutcome:
        (repo_root / "plan.txt").write_text("plan\n", encoding="utf-8")
        return StubPlanningOutcome()

    monkeypatch.setattr("continuous_refactoring.loop.run_planning", fake_run_planning)

    exit_code = continuous_refactoring.run_loop(make_run_loop_args(repo_root, max_refactors=1))

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Planning: awaiting human review — phase 2 has a decision gap" in output

    summary = _read_single_run_summary(repo_root)
    assert summary["counts"]["commits_created"] == 1
    attempts = summary["attempts"]
    assert len(attempts) == 1
    assert attempts[0]["commit_phase"] == "planning"


def test_run_stops_after_max_consecutive_failures(
    run_loop_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Relies on default max_attempts=None -> 1 attempt per target; one agent failure
    # per target increments consecutive_failures exactly once.
    repo_root = run_loop_env
    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", _failing_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    # Write a JSONL with 5 targets so we have enough attempts
    targets_file = tmp_path / "targets.jsonl"
    lines = []
    for i in range(5):
        lines.append(json.dumps({
            "description": f"target-{i}",
            "files": [f"file{i}.py"],
        }))
    targets_file.write_text("\n".join(lines), encoding="utf-8")

    args = make_run_loop_args(
        repo_root,
        targets=targets_file,
        max_consecutive_failures=3,
        scope_instruction=None,
    )
    with pytest.raises(ContinuousRefactorError, match="3 consecutive failures"):
        continuous_refactoring.run_loop(args)


def test_run_resets_consecutive_counter_on_success(
    run_loop_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Relies on default max_attempts=None -> 1 attempt per target; counter semantics
    # would shift if retries were wired here.
    repo_root = run_loop_env

    call_count = 0

    def alternating_agent(**kwargs: object) -> CommandCapture:
        nonlocal call_count
        call_count += 1
        # Pattern: fail, fail, succeed, fail, fail, fail
        if call_count in (1, 2, 4, 5, 6):
            return _failing_agent(**kwargs)
        # Success: touch a file so there's a change
        rr = Path(str(kwargs.get("repo_root", "")))
        (rr / f"change{call_count}.txt").write_text("x\n", encoding="utf-8")
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", alternating_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    targets_file = tmp_path / "targets.jsonl"
    lines = []
    for i in range(6):
        lines.append(json.dumps({
            "description": f"target-{i}",
            "files": [f"file{i}.py"],
        }))
    targets_file.write_text("\n".join(lines), encoding="utf-8")

    args = make_run_loop_args(
        repo_root,
        targets=targets_file,
        max_consecutive_failures=3,
        scope_instruction=None,
    )
    with pytest.raises(ContinuousRefactorError, match="3 consecutive failures"):
        continuous_refactoring.run_loop(args)

    # Should have gotten through: fail, fail, succeed (reset), fail, fail, fail (stop)
    assert call_count == 6


def test_run_target_overrides(
    run_loop_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env

    captured_models: list[str] = []

    def model_capturing_agent(**kwargs: object) -> CommandCapture:
        captured_models.append(str(kwargs.get("model", "")))
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", model_capturing_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    targets_file = tmp_path / "targets.jsonl"
    targets_file.write_text(
        json.dumps({
            "description": "override target",
            "files": ["foo.py"],
            "model-override": "special-model",
        }),
        encoding="utf-8",
    )

    args = make_run_loop_args(
        repo_root,
        targets=targets_file,
        model="default-model",
        scope_instruction=None,
    )
    continuous_refactoring.run_loop(args)

    assert len(captured_models) == 1
    assert captured_models[0] == "special-model"


def test_run_undo_commit_on_validation_failure(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Relies on default max_attempts=None -> 1 attempt per target so the single
    # validation failure bubbles up as a consecutive failure immediately.
    repo_root = run_loop_env

    def committing_agent(**kwargs: object) -> CommandCapture:
        rr = Path(str(kwargs.get("repo_root", "")))
        (rr / "bad_change.txt").write_text("bad\n", encoding="utf-8")
        continuous_refactoring.run_command(["git", "add", "-A"], cwd=rr)
        continuous_refactoring.run_command(
            ["git", "commit", "-m", "agent commit"], cwd=rr,
        )
        return noop_agent(**kwargs)

    # Baseline passes, but validation after agent fails
    test_call_count = 0

    def baseline_passes_then_fails(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        nonlocal test_call_count
        test_call_count += 1
        # First call is the baseline check - pass it
        if test_call_count == 1:
            return noop_tests(test_command, repo_root, stdout_path, stderr_path)
        return failing_tests(test_command, repo_root, stdout_path, stderr_path)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", committing_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", baseline_passes_then_fails)

    args = make_run_loop_args(repo_root, max_refactors=1, max_consecutive_failures=1)
    with pytest.raises(ContinuousRefactorError, match="consecutive failures"):
        continuous_refactoring.run_loop(args)

    log = continuous_refactoring.run_command(
        ["git", "log", "--oneline"], cwd=repo_root,
    )
    assert "agent commit" not in log.stdout


def _repo_with_py_files(repo_root: Path) -> list[str]:
    """Seed an already-initialized repo with three tracked ``.py`` files."""
    (repo_root / "src").mkdir(parents=True, exist_ok=True)
    (repo_root / "tests").mkdir(parents=True, exist_ok=True)
    (repo_root / "src" / "foo.py").write_text("# foo\n", encoding="utf-8")
    (repo_root / "src" / "bar.py").write_text("# bar\n", encoding="utf-8")
    (repo_root / "tests" / "test_foo.py").write_text("# test\n", encoding="utf-8")
    continuous_refactoring.run_command(["git", "add", "."], cwd=repo_root)
    continuous_refactoring.run_command(
        ["git", "commit", "-m", "add py files"], cwd=repo_root,
    )
    return ["src/bar.py", "src/foo.py", "tests/test_foo.py"]


def test_run_extensions_targeting(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env
    _repo_with_py_files(repo_root)

    captured_prompts: list[str] = []

    def capture_agent(**kwargs: object) -> CommandCapture:
        captured_prompts.append(str(kwargs.get("prompt", "")))
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", capture_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    args = make_run_loop_args(repo_root, extensions=".py", max_refactors=1)
    continuous_refactoring.run_loop(args)

    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    # Per-file Target: prompt should contain exactly one concrete .py path.
    matched = [f for f in ("src/foo.py", "src/bar.py", "tests/test_foo.py") if f in prompt]
    assert len(matched) == 1, matched


def test_run_extensions_expands_to_multiple_targets(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env
    tracked = _repo_with_py_files(repo_root)

    captured_prompts: list[str] = []

    def capture_agent(**kwargs: object) -> CommandCapture:
        captured_prompts.append(str(kwargs.get("prompt", "")))
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", capture_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    args = make_run_loop_args(repo_root, extensions=".py", max_refactors=99)
    continuous_refactoring.run_loop(args)

    assert len(captured_prompts) == len(tracked)
    hit = {f for f in tracked if any(f in p for p in captured_prompts)}
    assert hit == set(tracked)


def test_run_globs_targeting(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env
    _repo_with_py_files(repo_root)

    captured_prompts: list[str] = []

    def capture_agent(**kwargs: object) -> CommandCapture:
        captured_prompts.append(str(kwargs.get("prompt", "")))
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", capture_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    args = make_run_loop_args(repo_root, globs="src/**/*.py", max_refactors=1)
    continuous_refactoring.run_loop(args)

    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    matched = [f for f in ("src/foo.py", "src/bar.py") if f in prompt]
    assert len(matched) == 1, matched
    assert "tests/test_foo.py" not in prompt


def test_run_max_refactors_samples_from_extensions(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env
    (repo_root / "src").mkdir(parents=True, exist_ok=True)
    for name in ("a.py", "b.py", "c.py", "d.py", "e.py"):
        (repo_root / "src" / name).write_text(f"# {name}\n", encoding="utf-8")
    continuous_refactoring.run_command(["git", "add", "."], cwd=repo_root)
    continuous_refactoring.run_command(
        ["git", "commit", "-m", "five py"], cwd=repo_root,
    )

    agent_calls = 0

    def counting_agent(**kwargs: object) -> CommandCapture:
        nonlocal agent_calls
        agent_calls += 1
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", counting_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    args = make_run_loop_args(repo_root, extensions=".py", max_refactors=3)
    continuous_refactoring.run_loop(args)

    assert agent_calls == 3


def test_cli_does_not_cap_max_refactors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)

    args = argparse.Namespace(
        agent="codex",
        model="m",
        effort="xhigh",
        validation_command="true",
        extensions=".py",
        globs=None,
        targets=None,
        paths=None,
        scope_instruction=None,
        timeout=None,
        refactoring_prompt=None,
        fix_prompt=None,
        show_agent_logs=False,
        show_command_logs=False,
        repo_root=repo_root,
        max_attempts=None,
        max_refactors=20,
        commit_message_prefix="continuous refactor",
        max_consecutive_failures=3,
    )

    calls: list[argparse.Namespace] = []

    def fake_run_loop(passed: argparse.Namespace) -> int:
        calls.append(passed)
        return 0

    monkeypatch.setattr("continuous_refactoring.cli.run_loop", fake_run_loop)

    from continuous_refactoring.cli import _handle_run

    with pytest.raises(SystemExit) as exc_info:
        _handle_run(args)
    assert exc_info.value.code == 0
    assert len(calls) == 1
    assert calls[0].max_refactors == 20


def test_run_random_fallback_targeting(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env
    # Add a Python file so there's something to find
    (repo_root / "hello.py").write_text("print('hi')\n", encoding="utf-8")
    continuous_refactoring.run_command(["git", "add", "hello.py"], cwd=repo_root)
    continuous_refactoring.run_command(
        ["git", "commit", "-m", "add hello"], cwd=repo_root,
    )

    captured_prompts: list[str] = []

    def capture_agent(**kwargs: object) -> CommandCapture:
        captured_prompts.append(str(kwargs.get("prompt", "")))
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", capture_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    args = make_run_loop_args(repo_root, max_refactors=1, scope_instruction=None)
    # With no targeting args and no scope_instruction, resolve_targets falls back to
    # random files from git ls-files
    continuous_refactoring.run_loop(args)

    assert len(captured_prompts) == 1
    # Should have target files from the random selection
    assert "## Target Files" in captured_prompts[0]


def test_run_ctrl_c_discards_and_summarizes(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = run_loop_env

    def interrupting_agent(**kwargs: object) -> CommandCapture:
        raise KeyboardInterrupt

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", interrupting_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    args = make_run_loop_args(repo_root, max_refactors=1)
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 130
    captured = capsys.readouterr()
    assert "Artifact logs:" in captured.err


def test_cli_errors_when_no_targets_and_no_scope_instruction(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env

    args = argparse.Namespace(
        agent="codex",
        model="m",
        effort="xhigh",
        validation_command="true",
        extensions=None,
        globs=None,
        targets=None,
        paths=None,
        scope_instruction=None,
        timeout=None,
        refactoring_prompt=None,
        fix_prompt=None,
        show_agent_logs=False,
        show_command_logs=False,
        repo_root=repo_root,
    )

    from continuous_refactoring.cli import _validate_targeting

    with pytest.raises(SystemExit) as exc_info:
        _validate_targeting(args)
    assert exc_info.value.code == 2


def test_run_samples_targets_when_max_refactors_lt_total(
    run_loop_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env

    agent_calls = 0

    def counting_agent(**kwargs: object) -> CommandCapture:
        nonlocal agent_calls
        agent_calls += 1
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", counting_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    targets_file = tmp_path / "targets.jsonl"
    lines = []
    for i in range(10):
        lines.append(json.dumps({
            "description": f"target-{i}",
            "files": [f"file{i}.py"],
        }))
    targets_file.write_text("\n".join(lines), encoding="utf-8")

    args = make_run_loop_args(
        repo_root,
        targets=targets_file,
        max_refactors=3,
        scope_instruction=None,
    )
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    assert agent_calls == 3


def _count_validation_calls(stdout_path: object) -> bool:
    """True when the stdout_path points at a per-attempt validation log."""
    return "attempt-" in str(stdout_path)


def test_run_retries_on_validation_failure_and_succeeds(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env

    agent_calls = 0
    validation_calls = 0

    def touching_agent(**kwargs: object) -> CommandCapture:
        nonlocal agent_calls
        agent_calls += 1
        rr = Path(str(kwargs.get("repo_root", "")))
        (rr / f"touched-{agent_calls}.txt").write_text("x\n", encoding="utf-8")
        return noop_agent(**kwargs)

    def tests_fail_then_pass(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        nonlocal validation_calls
        if not _count_validation_calls(stdout_path):
            return noop_tests(test_command, repo_root, stdout_path, stderr_path)
        validation_calls += 1
        if validation_calls == 1:
            return failing_tests(test_command, repo_root, stdout_path, stderr_path)
        return noop_tests(test_command, repo_root, stdout_path, stderr_path)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", touching_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", tests_fail_then_pass)

    args = make_run_loop_args(repo_root, max_refactors=1, max_attempts=3)
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    assert agent_calls == 2
    assert validation_calls == 2
    log = continuous_refactoring.run_command(
        ["git", "log", "--oneline"], cwd=repo_root,
    )
    refactor_commits = [
        line for line in log.stdout.splitlines() if "continuous refactor" in line
    ]
    assert len(refactor_commits) == 1


def test_run_exhausts_max_attempts_on_persistent_validation_failure(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env

    agent_calls = 0

    def touching_agent(**kwargs: object) -> CommandCapture:
        nonlocal agent_calls
        agent_calls += 1
        rr = Path(str(kwargs.get("repo_root", "")))
        (rr / f"t-{agent_calls}.txt").write_text("x\n", encoding="utf-8")
        return noop_agent(**kwargs)

    def baseline_pass_validation_fail(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        if not _count_validation_calls(stdout_path):
            return noop_tests(test_command, repo_root, stdout_path, stderr_path)
        return failing_tests(test_command, repo_root, stdout_path, stderr_path)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", touching_agent)
    monkeypatch.setattr(
        "continuous_refactoring.loop.run_tests", baseline_pass_validation_fail,
    )

    args = make_run_loop_args(
        repo_root,
        max_refactors=1,
        max_attempts=3,
        max_consecutive_failures=5,
    )
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    assert agent_calls == 3
    log = continuous_refactoring.run_command(
        ["git", "log", "--oneline"], cwd=repo_root,
    )
    assert "continuous refactor" not in log.stdout


def test_run_exhausts_max_attempts_on_persistent_agent_failure(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env

    agent_calls = 0
    validation_calls = 0

    def failing_agent(**kwargs: object) -> CommandCapture:
        nonlocal agent_calls
        agent_calls += 1
        return _failing_agent(**kwargs)

    def counting_tests(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        nonlocal validation_calls
        if _count_validation_calls(stdout_path):
            validation_calls += 1
        return noop_tests(test_command, repo_root, stdout_path, stderr_path)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", failing_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", counting_tests)

    args = make_run_loop_args(
        repo_root,
        max_refactors=1,
        max_attempts=3,
        max_consecutive_failures=1,
    )
    with pytest.raises(ContinuousRefactorError, match="1 consecutive failures"):
        continuous_refactoring.run_loop(args)

    assert agent_calls == 3
    assert validation_calls == 0
    log = continuous_refactoring.run_command(
        ["git", "log", "--oneline"], cwd=repo_root,
    )
    assert "continuous refactor" not in log.stdout


def test_run_retry_prompt_uses_sanitized_failure_context(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env

    captured_prompts: list[str] = []

    def capture_agent(**kwargs: object) -> CommandCapture:
        captured_prompts.append(str(kwargs.get("prompt", "")))
        rr = Path(str(kwargs.get("repo_root", "")))
        (rr / f"touched-{len(captured_prompts)}.txt").write_text("x\n", encoding="utf-8")
        return noop_agent(**kwargs)

    def failing_tests_with_marker(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text(
            "codex exec --model fake VERY-HUGE-PROMPT\nFOOBAR-MARKER failed\n",
            encoding="utf-8",
        )
        stderr_path.write_text("", encoding="utf-8")
        return CommandCapture(
            command=("pytest",),
            returncode=1,
            stdout="codex exec --model fake VERY-HUGE-PROMPT\nFOOBAR-MARKER failed\n",
            stderr="",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )

    validation_call = 0

    def tests_fail_then_pass(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        nonlocal validation_call
        if not _count_validation_calls(stdout_path):
            return noop_tests(test_command, repo_root, stdout_path, stderr_path)
        validation_call += 1
        if validation_call == 1:
            return failing_tests_with_marker(
                test_command, repo_root, stdout_path, stderr_path,
            )
        return noop_tests(test_command, repo_root, stdout_path, stderr_path)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", capture_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", tests_fail_then_pass)

    args = make_run_loop_args(repo_root, max_refactors=1, max_attempts=3)
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    assert len(captured_prompts) == 2
    assert "## Retry Context" not in captured_prompts[0]
    assert "## Retry Context" in captured_prompts[1]
    assert "validation failed after refactor" in captured_prompts[1]
    assert "FOOBAR-MARKER" not in captured_prompts[1]
    assert "VERY-HUGE-PROMPT" not in captured_prompts[1]


def test_run_records_retry_and_abandon_transitions_with_failure_docs(
    run_loop_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env

    agent_calls = 0

    def touching_agent(**kwargs: object) -> CommandCapture:
        nonlocal agent_calls
        agent_calls += 1
        rr = Path(str(kwargs.get("repo_root", "")))
        (rr / f"touch-{agent_calls}.txt").write_text("x\n", encoding="utf-8")
        return noop_agent(**kwargs)

    validation_calls = 0

    def fail_twice_then_pass(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        nonlocal validation_calls
        if not _count_validation_calls(stdout_path):
            return noop_tests(test_command, repo_root, stdout_path, stderr_path)
        validation_calls += 1
        if validation_calls <= 2:
            return failing_tests(test_command, repo_root, stdout_path, stderr_path)
        return noop_tests(test_command, repo_root, stdout_path, stderr_path)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", touching_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", fail_twice_then_pass)

    targets_file = tmp_path / "targets.jsonl"
    targets_file.write_text(
        "\n".join(
            [
                json.dumps({"description": "target-a", "files": ["a.py"]}),
                json.dumps({"description": "target-b", "files": ["b.py"]}),
            ]
        ),
        encoding="utf-8",
    )

    args = make_run_loop_args(
        repo_root,
        targets=targets_file,
        max_attempts=2,
        max_consecutive_failures=3,
        scope_instruction=None,
    )
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    assert agent_calls == 3

    summary = _read_single_run_summary(repo_root)
    attempts = summary["attempts"]
    assert attempts[0]["decision"] == "abandon"
    assert attempts[0]["retry_recommendation"] == "new-target"
    assert attempts[0]["call_role"] == "validation"
    assert attempts[0]["reason_doc_path"]
    assert attempts[1]["decision"] == "commit"

    events = _read_single_run_events(repo_root)
    call_roles = [event.get("call_role") for event in events]
    assert "refactor" in call_roles
    assert "validation" in call_roles
    transitions = [
        (event.get("decision"), event.get("retry_recommendation"))
        for event in events
        if event.get("event") == "target_transition"
    ]
    assert ("retry", "same-target") in transitions
    assert ("abandon", "new-target") in transitions

    snapshots = sorted(
        continuous_refactoring.config.failure_snapshots_dir(repo_root).glob("*.md")
    )
    assert len(snapshots) == 2
    reason_doc = snapshots[-1].read_text(encoding="utf-8")
    assert 'decision: "abandon"' in reason_doc
    assert 'retry_recommendation: "new-target"' in reason_doc
    assert 'call_role: "validation"' in reason_doc


def test_run_successful_retry_clears_reason_doc_from_summary(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", noop_agent)

    validation_calls = 0

    def fail_once_then_pass(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        nonlocal validation_calls
        if not _count_validation_calls(stdout_path):
            return noop_tests(test_command, repo_root, stdout_path, stderr_path)
        validation_calls += 1
        if validation_calls == 1:
            return failing_tests(test_command, repo_root, stdout_path, stderr_path)
        return noop_tests(test_command, repo_root, stdout_path, stderr_path)

    monkeypatch.setattr("continuous_refactoring.loop.run_tests", fail_once_then_pass)

    exit_code = continuous_refactoring.run_loop(
        make_run_loop_args(repo_root, max_refactors=1, max_attempts=2)
    )

    assert exit_code == 0
    summary = _read_single_run_summary(repo_root)
    attempts = summary["attempts"]
    assert attempts[0]["decision"] == "commit"
    assert attempts[0]["reason_doc_path"] is None


def test_run_planning_failure_writes_reason_doc_and_logs_stage(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env
    live_dir = repo_root / ".migrations"
    live_dir.mkdir()
    monkeypatch.setattr(
        "continuous_refactoring.loop._resolve_live_migrations_dir",
        lambda _repo_root: live_dir,
    )
    monkeypatch.setattr(
        "continuous_refactoring.loop.classify_target",
        lambda *_args, **_kwargs: "needs-plan",
    )
    def timeout_planning_stage(**kwargs: object) -> CommandCapture:
        raise ContinuousRefactorError("codex timed out after 5s")

    monkeypatch.setattr(
        "continuous_refactoring.planning.maybe_run_agent",
        timeout_planning_stage,
    )

    args = make_run_loop_args(
        repo_root,
        max_refactors=1,
        max_consecutive_failures=1,
    )
    with pytest.raises(ContinuousRefactorError, match="1 consecutive failures"):
        continuous_refactoring.run_loop(args)

    events = _read_single_run_events(repo_root)
    planning_events = [
        event for event in events if event.get("call_role") == "planning.approaches"
    ]
    assert planning_events
    assert any(event.get("call_status") == "failed" for event in planning_events)

    snapshots = sorted(
        continuous_refactoring.config.failure_snapshots_dir(repo_root).glob("*.md")
    )
    reason_doc = snapshots[-1].read_text(encoding="utf-8")
    assert 'call_role: "planning.approaches"' in reason_doc
    assert 'decision: "abandon"' in reason_doc


def test_run_phase_ready_check_failure_logs_phase_ready_role(
    run_loop_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env
    live_dir = tmp_path / "live-migrations"
    live_dir.mkdir()
    _write_live_manifest(live_dir)
    monkeypatch.setattr(
        "continuous_refactoring.loop._resolve_live_migrations_dir",
        lambda _repo_root: live_dir,
    )

    def timeout_ready_check(**kwargs: object) -> CommandCapture:
        raise ContinuousRefactorError("codex timed out after 5s")

    monkeypatch.setattr(
        "continuous_refactoring.phases.maybe_run_agent", timeout_ready_check,
    )

    args = make_run_loop_args(
        repo_root,
        max_refactors=1,
        max_consecutive_failures=1,
    )
    with pytest.raises(ContinuousRefactorError, match="1 consecutive failures"):
        continuous_refactoring.run_loop(args)

    events = _read_single_run_events(repo_root)
    assert any(
        event.get("call_role") == "phase.ready-check"
        and event.get("call_status") == "failed"
        for event in events
    )

    snapshots = sorted(
        continuous_refactoring.config.failure_snapshots_dir(repo_root).glob("*.md")
    )
    reason_doc = snapshots[-1].read_text(encoding="utf-8")
    assert 'call_role: "phase.ready-check"' in reason_doc


def test_run_phase_execute_validation_failure_logs_phase_validation_role(
    run_loop_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env
    live_dir = tmp_path / "live-migrations"
    live_dir.mkdir()
    _write_live_manifest(live_dir)
    monkeypatch.setattr(
        "continuous_refactoring.loop._resolve_live_migrations_dir",
        lambda _repo_root: live_dir,
    )

    def ready_then_execute(**kwargs: object) -> CommandCapture:
        stdout_path = Path(str(kwargs["stdout_path"]))
        stderr_path = Path(str(kwargs["stderr_path"]))
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        if "phase-ready-check" in str(stdout_path):
            stdout = "ready: yes\n"
        else:
            stdout = "done\n"
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return CommandCapture(
            command=("fake",),
            returncode=0,
            stdout=stdout,
            stderr="",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )

    monkeypatch.setattr("continuous_refactoring.phases.maybe_run_agent", ready_then_execute)
    monkeypatch.setattr("continuous_refactoring.phases.run_tests", failing_tests)

    args = make_run_loop_args(
        repo_root,
        max_refactors=1,
        max_consecutive_failures=1,
    )
    with pytest.raises(ContinuousRefactorError, match="1 consecutive failures"):
        continuous_refactoring.run_loop(args)

    events = _read_single_run_events(repo_root)
    assert any(
        event.get("call_role") == "phase.execute"
        and event.get("call_status") == "finished"
        for event in events
    )
    assert any(
        event.get("call_role") == "phase.validation"
        and event.get("call_status") == "failed"
        for event in events
    )

    snapshots = sorted(
        continuous_refactoring.config.failure_snapshots_dir(repo_root).glob("*.md")
    )
    reason_doc = snapshots[-1].read_text(encoding="utf-8")
    assert 'call_role: "phase.validation"' in reason_doc


def test_run_phase_execute_validation_infra_failure_logs_phase_validation_role(
    run_loop_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env
    live_dir = tmp_path / "live-migrations"
    live_dir.mkdir()
    _write_live_manifest(live_dir)
    monkeypatch.setattr(
        "continuous_refactoring.loop._resolve_live_migrations_dir",
        lambda _repo_root: live_dir,
    )

    def ready_then_execute(**kwargs: object) -> CommandCapture:
        stdout_path = Path(str(kwargs["stdout_path"]))
        stderr_path = Path(str(kwargs["stderr_path"]))
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        stdout = "ready: yes\n" if "phase-ready-check" in str(stdout_path) else "done\n"
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return CommandCapture(
            command=("fake",),
            returncode=0,
            stdout=stdout,
            stderr="",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )

    def validation_timeout(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        raise ContinuousRefactorError("pytest timed out after 5s")

    monkeypatch.setattr("continuous_refactoring.phases.maybe_run_agent", ready_then_execute)
    monkeypatch.setattr("continuous_refactoring.phases.run_tests", validation_timeout)

    args = make_run_loop_args(
        repo_root,
        max_refactors=1,
        max_consecutive_failures=1,
    )
    with pytest.raises(ContinuousRefactorError, match="1 consecutive failures"):
        continuous_refactoring.run_loop(args)

    events = _read_single_run_events(repo_root)
    assert any(
        event.get("call_role") == "phase.validation"
        and event.get("call_status") == "failed"
        for event in events
    )


def test_run_retry_prompt_includes_fix_amendment(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env

    captured_prompts: list[str] = []

    def capture_agent(**kwargs: object) -> CommandCapture:
        captured_prompts.append(str(kwargs.get("prompt", "")))
        rr = Path(str(kwargs.get("repo_root", "")))
        (rr / f"touched-{len(captured_prompts)}.txt").write_text("x\n", encoding="utf-8")
        return noop_agent(**kwargs)

    def tests_fail_then_pass(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        if not _count_validation_calls(stdout_path):
            return noop_tests(test_command, repo_root, stdout_path, stderr_path)
        # fail on the first per-attempt validation, pass after
        if not hasattr(tests_fail_then_pass, "called"):
            tests_fail_then_pass.called = True  # type: ignore[attr-defined]
            return failing_tests(test_command, repo_root, stdout_path, stderr_path)
        return noop_tests(test_command, repo_root, stdout_path, stderr_path)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", capture_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", tests_fail_then_pass)

    args = make_run_loop_args(repo_root, max_refactors=1, max_attempts=3)
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    assert len(captured_prompts) == 2
    assert "Do not commit anything until all checks are green" not in captured_prompts[0]
    assert "Do not commit anything until all checks are green" in captured_prompts[1]


def test_run_max_attempts_zero_is_unlimited_until_success(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env

    agent_calls = 0

    def touching_agent(**kwargs: object) -> CommandCapture:
        nonlocal agent_calls
        agent_calls += 1
        # Safety cap — catches a runaway unlimited loop.
        if agent_calls > 20:
            raise RuntimeError("runaway retry loop")
        rr = Path(str(kwargs.get("repo_root", "")))
        (rr / f"t-{agent_calls}.txt").write_text("x\n", encoding="utf-8")
        return noop_agent(**kwargs)

    validation_calls = 0

    def fail_five_then_pass(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        nonlocal validation_calls
        if not _count_validation_calls(stdout_path):
            return noop_tests(test_command, repo_root, stdout_path, stderr_path)
        validation_calls += 1
        if validation_calls <= 5:
            return failing_tests(test_command, repo_root, stdout_path, stderr_path)
        return noop_tests(test_command, repo_root, stdout_path, stderr_path)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", touching_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", fail_five_then_pass)

    args = make_run_loop_args(repo_root, max_refactors=1, max_attempts=0)
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    assert agent_calls == 6
    log = continuous_refactoring.run_command(
        ["git", "log", "--oneline"], cwd=repo_root,
    )
    refactor_commits = [
        line for line in log.stdout.splitlines() if "continuous refactor" in line
    ]
    assert len(refactor_commits) == 1


def test_run_custom_fix_prompt_file(
    run_loop_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env

    fix_prompt = tmp_path / "fix.md"
    fix_prompt.write_text("CUSTOM-FIX-BANNER: be very careful\n", encoding="utf-8")

    captured_prompts: list[str] = []

    def capture_agent(**kwargs: object) -> CommandCapture:
        captured_prompts.append(str(kwargs.get("prompt", "")))
        rr = Path(str(kwargs.get("repo_root", "")))
        (rr / f"touched-{len(captured_prompts)}.txt").write_text("x\n", encoding="utf-8")
        return noop_agent(**kwargs)

    def tests_fail_then_pass(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        if not _count_validation_calls(stdout_path):
            return noop_tests(test_command, repo_root, stdout_path, stderr_path)
        if not hasattr(tests_fail_then_pass, "called"):
            tests_fail_then_pass.called = True  # type: ignore[attr-defined]
            return failing_tests(test_command, repo_root, stdout_path, stderr_path)
        return noop_tests(test_command, repo_root, stdout_path, stderr_path)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", capture_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", tests_fail_then_pass)

    args = make_run_loop_args(
        repo_root,
        max_refactors=1,
        max_attempts=3,
        fix_prompt=fix_prompt,
    )
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    assert len(captured_prompts) == 2
    assert "CUSTOM-FIX-BANNER" not in captured_prompts[0]
    assert "CUSTOM-FIX-BANNER" in captured_prompts[1]
    assert "Do not commit anything until all checks are green" not in captured_prompts[1]


def test_run_undo_commit_between_retries(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env

    agent_calls = 0

    def committing_then_clean_agent(**kwargs: object) -> CommandCapture:
        nonlocal agent_calls
        agent_calls += 1
        rr = Path(str(kwargs.get("repo_root", "")))
        if agent_calls == 1:
            (rr / "bad_change.txt").write_text("bad\n", encoding="utf-8")
            continuous_refactoring.run_command(["git", "add", "-A"], cwd=rr)
            continuous_refactoring.run_command(
                ["git", "commit", "-m", "agent bad commit"], cwd=rr,
            )
        else:
            (rr / "good_change.txt").write_text("good\n", encoding="utf-8")
        return noop_agent(**kwargs)

    validation_calls = 0

    def fail_then_pass(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        nonlocal validation_calls
        if not _count_validation_calls(stdout_path):
            return noop_tests(test_command, repo_root, stdout_path, stderr_path)
        validation_calls += 1
        if validation_calls == 1:
            return failing_tests(test_command, repo_root, stdout_path, stderr_path)
        return noop_tests(test_command, repo_root, stdout_path, stderr_path)

    monkeypatch.setattr(
        "continuous_refactoring.loop.maybe_run_agent", committing_then_clean_agent,
    )
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", fail_then_pass)

    args = make_run_loop_args(repo_root, max_refactors=1, max_attempts=3)
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    log = continuous_refactoring.run_command(
        ["git", "log", "--oneline"], cwd=repo_root,
    )
    assert "agent bad commit" not in log.stdout
    refactor_commits = [
        line for line in log.stdout.splitlines() if "continuous refactor" in line
    ]
    assert len(refactor_commits) == 1


def test_run_agent_failure_undoes_commit_before_retry(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Agent that commits then exits non-zero must not leak the commit into retry 2."""
    repo_root = run_loop_env

    base_sha = continuous_refactoring.run_command(
        ["git", "rev-parse", "HEAD"], cwd=repo_root,
    ).stdout.strip()

    agent_calls = 0
    retry2_head_before: list[str] = []

    def commit_then_fail_then_clean(**kwargs: object) -> CommandCapture:
        nonlocal agent_calls
        agent_calls += 1
        rr = Path(str(kwargs.get("repo_root", "")))
        if agent_calls == 1:
            # Agent commits a bad change, then exits non-zero (mirrors timeout
            # or OOM after a commit).
            (rr / "bad_change.txt").write_text("bad\n", encoding="utf-8")
            continuous_refactoring.run_command(["git", "add", "-A"], cwd=rr)
            continuous_refactoring.run_command(
                ["git", "commit", "-m", "agent bad commit before crash"], cwd=rr,
            )
            return _failing_agent(**kwargs)
        if agent_calls == 2:
            # Capture HEAD at the start of retry 2 — must be the pre-retry-1 HEAD
            # (the bad commit must have been undone before retry 2 began).
            retry2_head_before.append(
                continuous_refactoring.run_command(
                    ["git", "rev-parse", "HEAD"], cwd=rr,
                ).stdout.strip()
            )
            (rr / "good_change.txt").write_text("good\n", encoding="utf-8")
        return noop_agent(**kwargs)

    monkeypatch.setattr(
        "continuous_refactoring.loop.maybe_run_agent", commit_then_fail_then_clean,
    )
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    args = make_run_loop_args(repo_root, max_refactors=1, max_attempts=3)
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    assert agent_calls == 2
    # Retry 2 must have started from the original base — not from the bad commit.
    assert retry2_head_before == [base_sha]
    log = continuous_refactoring.run_command(
        ["git", "log", "--oneline"], cwd=repo_root,
    )
    assert "agent bad commit before crash" not in log.stdout
    refactor_commits = [
        line for line in log.stdout.splitlines() if "continuous refactor" in line
    ]
    assert len(refactor_commits) == 1
