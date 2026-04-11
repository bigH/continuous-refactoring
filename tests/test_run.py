from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

import continuous_refactoring
import continuous_refactoring.loop
from continuous_refactoring.artifacts import CommandCapture, ContinuousRefactorError
from continuous_refactoring.targeting import Target


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    continuous_refactoring.run_command(["git", "init", "-b", "main"], cwd=path)
    continuous_refactoring.run_command(
        ["git", "config", "user.email", "test@example.com"], cwd=path,
    )
    continuous_refactoring.run_command(
        ["git", "config", "user.name", "Test User"], cwd=path,
    )
    (path / "README.md").write_text("seed\n", encoding="utf-8")
    continuous_refactoring.run_command(["git", "add", "README.md"], cwd=path)
    continuous_refactoring.run_command(["git", "commit", "-m", "init"], cwd=path)


def _make_run_args(
    repo_root: Path,
    *,
    agent: str = "codex",
    model: str = "fake-model",
    effort: str = "xhigh",
    validation_command: str | None = None,
    scope_instruction: str | None = "general cleanup",
    timeout: int | None = None,
    refactoring_prompt: Path | None = None,
    fix_prompt: Path | None = None,
    extensions: str | None = None,
    globs: str | None = None,
    targets: Path | None = None,
    paths: str | None = None,
    max_attempts: int | None = None,
    max_refactors: int | None = None,
    no_push: bool = True,
    push_remote: str = "origin",
    commit_message_prefix: str = "continuous refactor",
    max_consecutive_failures: int = 3,
) -> argparse.Namespace:
    test_script = repo_root.parent / "check_tests.py"
    if not test_script.exists():
        test_script.write_text("print('tests ok')\n", encoding="utf-8")
    return argparse.Namespace(
        agent=agent,
        model=model,
        effort=effort,
        validation_command=validation_command or f"{sys.executable} {test_script}",
        extensions=extensions,
        globs=globs,
        targets=targets,
        paths=paths,
        scope_instruction=scope_instruction,
        timeout=timeout,
        refactoring_prompt=refactoring_prompt,
        fix_prompt=fix_prompt,
        show_agent_logs=False,
        show_command_logs=False,
        repo_root=repo_root,
        max_attempts=max_attempts,
        max_refactors=max_refactors,
        no_push=no_push,
        push_remote=push_remote,
        commit_message_prefix=commit_message_prefix,
        max_consecutive_failures=max_consecutive_failures,
    )


def _noop_agent(**kwargs: object) -> CommandCapture:
    stdout_path = kwargs.get("stdout_path")
    stderr_path = kwargs.get("stderr_path")
    if stdout_path:
        Path(stdout_path).parent.mkdir(parents=True, exist_ok=True)
        Path(stdout_path).write_text("noop\n", encoding="utf-8")
    if stderr_path:
        Path(stderr_path).parent.mkdir(parents=True, exist_ok=True)
        Path(stderr_path).write_text("", encoding="utf-8")
    return CommandCapture(
        command=("fake",),
        returncode=0,
        stdout="noop\n",
        stderr="",
        stdout_path=Path(stdout_path) if stdout_path else Path("/dev/null"),
        stderr_path=Path(stderr_path) if stderr_path else Path("/dev/null"),
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


def _noop_tests(
    test_command: str,
    repo_root: Path,
    stdout_path: Path,
    stderr_path: Path,
    **kwargs: object,
) -> CommandCapture:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text("ok\n", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    return CommandCapture(
        command=("pytest",),
        returncode=0,
        stdout="ok\n",
        stderr="",
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )


def _failing_tests(
    test_command: str,
    repo_root: Path,
    stdout_path: Path,
    stderr_path: Path,
    **kwargs: object,
) -> CommandCapture:
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


def test_run_creates_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))
    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", _noop_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", _noop_tests)

    args = _make_run_args(repo_root, max_refactors=1)
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    branch = continuous_refactoring.current_branch(repo_root)
    assert re.match(r"^refactor-\d{8}T\d{6}$", branch)


def test_run_pushes_after_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
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
        return _noop_agent(**kwargs)

    def tracking_push(repo_root: Path, remote: str, branch: str) -> None:
        push_calls.append((remote, branch))

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", touching_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", _noop_tests)
    monkeypatch.setattr("continuous_refactoring.loop.git_push", tracking_push)

    args = _make_run_args(repo_root, max_refactors=1, no_push=False)
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    assert len(push_calls) == 1
    assert push_calls[0][0] == "origin"


def test_run_no_push_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
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
        return _noop_agent(**kwargs)

    def tracking_push(repo_root: Path, remote: str, branch: str) -> None:
        push_calls.append((remote, branch))

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", touching_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", _noop_tests)
    monkeypatch.setattr("continuous_refactoring.loop.git_push", tracking_push)

    args = _make_run_args(repo_root, max_refactors=1, no_push=True)
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    assert len(push_calls) == 0


def test_run_stops_after_max_consecutive_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pytest

    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))
    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", _failing_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", _noop_tests)

    # Write a JSONL with 5 targets so we have enough attempts
    targets_file = tmp_path / "targets.jsonl"
    lines = []
    for i in range(5):
        lines.append(json.dumps({
            "description": f"target-{i}",
            "files": [f"file{i}.py"],
        }))
    targets_file.write_text("\n".join(lines), encoding="utf-8")

    args = _make_run_args(
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
    import pytest

    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
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
        return _noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", alternating_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", _noop_tests)

    targets_file = tmp_path / "targets.jsonl"
    lines = []
    for i in range(6):
        lines.append(json.dumps({
            "description": f"target-{i}",
            "files": [f"file{i}.py"],
        }))
    targets_file.write_text("\n".join(lines), encoding="utf-8")

    args = _make_run_args(
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
    _init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

    captured_models: list[str] = []

    def model_capturing_agent(**kwargs: object) -> CommandCapture:
        captured_models.append(str(kwargs.get("model", "")))
        return _noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", model_capturing_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", _noop_tests)

    targets_file = tmp_path / "targets.jsonl"
    targets_file.write_text(
        json.dumps({
            "description": "override target",
            "files": ["foo.py"],
            "model-override": "special-model",
        }),
        encoding="utf-8",
    )

    args = _make_run_args(
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
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
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
        return _noop_agent(**kwargs)

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
            return _noop_tests(test_command, repo_root, stdout_path, stderr_path)
        return _failing_tests(test_command, repo_root, stdout_path, stderr_path)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", committing_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", baseline_passes_then_fails)

    args = _make_run_args(repo_root, max_refactors=1, max_consecutive_failures=1)
    import pytest
    with pytest.raises(ContinuousRefactorError, match="consecutive failures"):
        continuous_refactoring.run_loop(args)

    log = continuous_refactoring.run_command(
        ["git", "log", "--oneline"], cwd=repo_root,
    )
    assert "agent commit" not in log.stdout


def test_run_extensions_targeting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

    captured_prompts: list[str] = []

    def capture_agent(**kwargs: object) -> CommandCapture:
        captured_prompts.append(str(kwargs.get("prompt", "")))
        return _noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", capture_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", _noop_tests)

    args = _make_run_args(repo_root, extensions=".py", max_refactors=1)
    continuous_refactoring.run_loop(args)

    assert len(captured_prompts) == 1
    assert "**/*.py" in captured_prompts[0]


def test_run_globs_targeting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

    captured_prompts: list[str] = []

    def capture_agent(**kwargs: object) -> CommandCapture:
        captured_prompts.append(str(kwargs.get("prompt", "")))
        return _noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", capture_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", _noop_tests)

    args = _make_run_args(repo_root, globs="src/**", max_refactors=1)
    continuous_refactoring.run_loop(args)

    assert len(captured_prompts) == 1
    assert "src/**" in captured_prompts[0]


def test_run_random_fallback_targeting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
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
        return _noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", capture_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", _noop_tests)

    args = _make_run_args(repo_root, max_refactors=1, scope_instruction=None)
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
    _init_repo(repo_root)
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()

    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

    def interrupting_agent(**kwargs: object) -> CommandCapture:
        raise KeyboardInterrupt

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", interrupting_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", _noop_tests)

    args = _make_run_args(repo_root, max_refactors=1)
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
    _init_repo(repo_root)
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
    _init_repo(repo_root)
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
        return _noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", counting_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", _noop_tests)

    targets_file = tmp_path / "targets.jsonl"
    lines = []
    for i in range(10):
        lines.append(json.dumps({
            "description": f"target-{i}",
            "files": [f"file{i}.py"],
        }))
    targets_file.write_text("\n".join(lines), encoding="utf-8")

    args = _make_run_args(
        repo_root,
        targets=targets_file,
        max_refactors=3,
        scope_instruction=None,
    )
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    assert agent_calls == 3
