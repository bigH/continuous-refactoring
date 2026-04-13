from __future__ import annotations

import argparse
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


def _write_fake_codex(bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "codex"
    script.write_text(
        """#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    args = sys.argv[1:]
    output_path = None
    repo_root = None
    for index, arg in enumerate(args):
        if arg == "--output-last-message":
            output_path = Path(args[index + 1])
        if arg == "--cd":
            repo_root = Path(args[index + 1])

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            os.environ.get("FAKE_CODEX_LAST_MESSAGE", ""),
            encoding="utf-8",
        )

    stdout_text = os.environ.get("FAKE_CODEX_STDOUT", "")
    if stdout_text:
        sys.stdout.write(stdout_text)
        sys.stdout.flush()

    stderr_text = os.environ.get("FAKE_CODEX_STDERR", "")
    if stderr_text:
        sys.stderr.write(stderr_text)
        sys.stderr.flush()

    relative_path = os.environ.get("FAKE_CODEX_TOUCH_FILE")
    if relative_path and repo_root is not None:
        destination = repo_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            os.environ.get("FAKE_CODEX_TOUCH_CONTENT", ""),
            encoding="utf-8",
        )

    return int(os.environ.get("FAKE_CODEX_EXIT_CODE", "0"))


if __name__ == "__main__":
    raise SystemExit(main())
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def _make_run_once_args(
    repo_root: Path,
    *,
    agent: str = "codex",
    model: str = "fake-model",
    effort: str = "xhigh",
    validation_command: str | None = None,
    scope_instruction: str | None = "general cleanup",
    timeout: int | None = None,
    refactoring_prompt: Path | None = None,
    extensions: str | None = None,
    globs: str | None = None,
    targets: Path | None = None,
    paths: str | None = None,
    use_branch: str | None = None,
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
        fix_prompt=None,
        show_agent_logs=False,
        show_command_logs=False,
        repo_root=repo_root,
        use_branch=use_branch,
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


def test_run_once_creates_branch(
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

    args = _make_run_once_args(repo_root)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0
    branch = continuous_refactoring.current_branch(repo_root)
    assert re.match(r"^cr/\d{8}T\d{6}$", branch)


def test_run_once_composes_prompt_with_taste(
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

    args = _make_run_once_args(repo_root)
    continuous_refactoring.run_once(args)

    assert len(captured_prompts) == 1
    assert "## Refactoring Taste" in captured_prompts[0]


def test_run_once_composes_prompt_with_target(
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

    args = _make_run_once_args(repo_root, paths="src/foo.py:src/bar.py")
    continuous_refactoring.run_once(args)

    assert len(captured_prompts) == 1
    assert "## Target Files" in captured_prompts[0]
    assert "src/foo.py" in captured_prompts[0]
    assert "src/bar.py" in captured_prompts[0]


def test_run_once_composes_prompt_with_scope(
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

    args = _make_run_once_args(repo_root, scope_instruction="focus on error handling")
    continuous_refactoring.run_once(args)

    assert len(captured_prompts) == 1
    assert "## Scope" in captured_prompts[0]
    assert "focus on error handling" in captured_prompts[0]


def test_run_once_validation_gate(
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

    def committing_agent(**kwargs: object) -> CommandCapture:
        rr = Path(str(kwargs.get("repo_root", "")))
        (rr / "new_file.txt").write_text("agent wrote this\n", encoding="utf-8")
        continuous_refactoring.run_command(["git", "add", "-A"], cwd=rr)
        continuous_refactoring.run_command(
            ["git", "commit", "-m", "agent commit"], cwd=rr,
        )
        return _noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", committing_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", _failing_tests)

    args = _make_run_once_args(repo_root)
    with pytest.raises(ContinuousRefactorError, match="Validation failed"):
        continuous_refactoring.run_once(args)

    # Commit should have been undone
    log = continuous_refactoring.run_command(
        ["git", "log", "--oneline"], cwd=repo_root,
    )
    assert "agent commit" not in log.stdout


def test_run_once_no_fix_retry(
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

    agent_call_count = 0

    def counting_agent(**kwargs: object) -> CommandCapture:
        nonlocal agent_call_count
        agent_call_count += 1
        return _noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", counting_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", _failing_tests)

    args = _make_run_once_args(repo_root)
    with pytest.raises(ContinuousRefactorError, match="Validation failed"):
        continuous_refactoring.run_once(args)

    assert agent_call_count == 1


def test_run_once_prints_branch_and_diff(
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
    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", _noop_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", _noop_tests)

    args = _make_run_once_args(repo_root)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Branch: cr/" in output


def test_run_once_timeout(
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

    def timeout_agent(**kwargs: object) -> CommandCapture:
        raise ContinuousRefactorError("Command timed out after 1s: fake")

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", timeout_agent)

    args = _make_run_once_args(repo_root, timeout=1)
    with pytest.raises(ContinuousRefactorError, match="timed out"):
        continuous_refactoring.run_once(args)


def test_run_once_uses_default_prompt(
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

    args = _make_run_once_args(repo_root)
    continuous_refactoring.run_once(args)

    assert len(captured_prompts) == 1
    assert "You are a continuous refactoring agent" in captured_prompts[0]


def test_ctrl_c_prints_file_paths(
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

    args = _make_run_once_args(repo_root)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 130
    captured = capsys.readouterr()
    assert "Artifact logs:" in captured.err


def test_run_once_use_branch_creates_when_absent(
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

    args = _make_run_once_args(repo_root, use_branch="my-cleanup")
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0
    assert continuous_refactoring.current_branch(repo_root) == "my-cleanup"


def test_run_once_use_branch_reuses_existing(
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

    # Pre-create the branch with a distinct commit so we can assert reuse.
    continuous_refactoring.run_command(
        ["git", "checkout", "-b", "my-cleanup"], cwd=repo_root,
    )
    (repo_root / "marker.txt").write_text("marker\n", encoding="utf-8")
    continuous_refactoring.run_command(["git", "add", "marker.txt"], cwd=repo_root)
    continuous_refactoring.run_command(
        ["git", "commit", "-m", "marker commit"], cwd=repo_root,
    )
    expected_head = continuous_refactoring.run_command(
        ["git", "rev-parse", "HEAD"], cwd=repo_root,
    ).stdout.strip()
    continuous_refactoring.run_command(["git", "checkout", "main"], cwd=repo_root)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", _noop_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", _noop_tests)

    args = _make_run_once_args(repo_root, use_branch="my-cleanup")
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0
    assert continuous_refactoring.current_branch(repo_root) == "my-cleanup"
    # Branch wasn't recreated from main: its history still contains marker commit.
    log = continuous_refactoring.run_command(
        ["git", "log", "--oneline"], cwd=repo_root,
    ).stdout
    assert "marker commit" in log
    # HEAD is still the marker commit (no agent changes to commit).
    current_head = continuous_refactoring.run_command(
        ["git", "rev-parse", "HEAD"], cwd=repo_root,
    ).stdout.strip()
    assert current_head == expected_head
