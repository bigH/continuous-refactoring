from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

import continuous_refactoring
import continuous_refactoring.loop
from continuous_refactoring.artifacts import CommandCapture, ContinuousRefactorError
from continuous_refactoring.targeting import Target

from conftest import (
    failing_tests,
    init_repo,
    make_run_loop_args,
    noop_agent,
    noop_tests,
)


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


def test_run_creates_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))
    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", noop_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    args = make_run_loop_args(repo_root, max_refactors=1)
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    branch = continuous_refactoring.current_branch(repo_root)
    assert re.match(r"^refactor-\d{8}T\d{6}$", branch)


def test_run_pushes_after_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

    push_calls: list[tuple[str, str]] = []

    def touching_agent(**kwargs: object) -> CommandCapture:
        rr = Path(str(kwargs.get("repo_root", "")))
        (rr / "touched.txt").write_text("touched\n", encoding="utf-8")
        return noop_agent(**kwargs)

    def tracking_push(repo_root: Path, remote: str, branch: str) -> None:
        push_calls.append((remote, branch))

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", touching_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)
    monkeypatch.setattr("continuous_refactoring.loop.git_push", tracking_push)

    args = make_run_loop_args(repo_root, max_refactors=1, no_push=False)
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    assert len(push_calls) == 1
    assert push_calls[0][0] == "origin"


def test_run_no_push_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

    push_calls: list[tuple[str, str]] = []

    def touching_agent(**kwargs: object) -> CommandCapture:
        rr = Path(str(kwargs.get("repo_root", "")))
        (rr / "touched.txt").write_text("touched\n", encoding="utf-8")
        return noop_agent(**kwargs)

    def tracking_push(repo_root: Path, remote: str, branch: str) -> None:
        push_calls.append((remote, branch))

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", touching_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)
    monkeypatch.setattr("continuous_refactoring.loop.git_push", tracking_push)

    args = make_run_loop_args(repo_root, max_refactors=1, no_push=True)
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    assert len(push_calls) == 0


def test_run_stops_after_max_consecutive_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Relies on default max_attempts=None -> 1 attempt per target; one agent failure
    # per target increments consecutive_failures exactly once.
    import pytest

    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Relies on default max_attempts=None -> 1 attempt per target; counter semantics
    # would shift if retries were wired here.
    import pytest

    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Relies on default max_attempts=None -> 1 attempt per target so the single
    # validation failure bubbles up as a consecutive failure immediately.
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

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
    import pytest
    with pytest.raises(ContinuousRefactorError, match="consecutive failures"):
        continuous_refactoring.run_loop(args)

    log = continuous_refactoring.run_command(
        ["git", "log", "--oneline"], cwd=repo_root,
    )
    assert "agent commit" not in log.stdout


def _repo_with_py_files(repo_root: Path) -> list[str]:
    """Seed a git repo with three tracked ``.py`` files; return the paths."""
    init_repo(repo_root)
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    _repo_with_py_files(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    tracked = _repo_with_py_files(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    _repo_with_py_files(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    (repo_root / "src").mkdir(parents=True, exist_ok=True)
    for name in ("a.py", "b.py", "c.py", "d.py", "e.py"):
        (repo_root / "src" / name).write_text(f"# {name}\n", encoding="utf-8")
    continuous_refactoring.run_command(["git", "add", "."], cwd=repo_root)
    continuous_refactoring.run_command(
        ["git", "commit", "-m", "five py"], cwd=repo_root,
    )

    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

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
    import pytest

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
        no_push=True,
        push_remote="origin",
        commit_message_prefix="continuous refactor",
        max_consecutive_failures=3,
        use_branch=None,
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    # Add a Python file so there's something to find
    (repo_root / "hello.py").write_text("print('hi')\n", encoding="utf-8")
    continuous_refactoring.run_command(["git", "add", "hello.py"], cwd=repo_root)
    continuous_refactoring.run_command(
        ["git", "commit", "-m", "add hello"], cwd=repo_root,
    )

    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pytest

    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pytest

    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

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


def test_run_retry_prompt_includes_previous_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

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
        stdout_path.write_text("FOOBAR-MARKER failed\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return CommandCapture(
            command=("pytest",),
            returncode=1,
            stdout="FOOBAR-MARKER failed\n",
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
    assert "FOOBAR-MARKER" not in captured_prompts[0]
    assert "FOOBAR-MARKER" in captured_prompts[1]


def test_run_retry_prompt_includes_fix_amendment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Agent that commits then exits non-zero must not leak the commit into retry 2."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

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


def test_run_use_branch_creates_when_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))
    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", noop_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    args = make_run_loop_args(repo_root, max_refactors=1, use_branch="long-lived-refactor")
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    assert continuous_refactoring.current_branch(repo_root) == "long-lived-refactor"


def test_run_use_branch_reuses_existing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

    # Pre-create the branch with a distinct commit so we can verify reuse.
    continuous_refactoring.run_command(
        ["git", "checkout", "-b", "long-lived-refactor"], cwd=repo_root,
    )
    (repo_root / "marker.txt").write_text("marker\n", encoding="utf-8")
    continuous_refactoring.run_command(["git", "add", "marker.txt"], cwd=repo_root)
    continuous_refactoring.run_command(
        ["git", "commit", "-m", "marker commit"], cwd=repo_root,
    )
    continuous_refactoring.run_command(["git", "checkout", "main"], cwd=repo_root)

    def touching_agent(**kwargs: object) -> CommandCapture:
        rr = Path(str(kwargs.get("repo_root", "")))
        (rr / "agent_change.txt").write_text("x\n", encoding="utf-8")
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", touching_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    args = make_run_loop_args(
        repo_root, max_refactors=1, use_branch="long-lived-refactor",
    )
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    assert continuous_refactoring.current_branch(repo_root) == "long-lived-refactor"
    # Branch history retains the pre-existing marker commit and gains the new one.
    log = continuous_refactoring.run_command(
        ["git", "log", "--oneline"], cwd=repo_root,
    ).stdout
    assert "marker commit" in log
    assert "continuous refactor" in log
