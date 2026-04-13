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
from continuous_refactoring.artifacts import CommandCapture, ContinuousRefactorError
from continuous_refactoring.config import default_taste_text, register_project


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=path, check=True, capture_output=True,
    )
    (path / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "."], cwd=path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True,
    )


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


def _make_run_once_args(
    repo_root: Path,
    *,
    agent: str = "codex",
    model: str = "fake-model",
    effort: str = "xhigh",
    scope_instruction: str | None = "general cleanup",
    targets: Path | None = None,
    paths: str | None = None,
) -> argparse.Namespace:
    test_script = repo_root.parent / "check_tests.py"
    if not test_script.exists():
        test_script.write_text("print('tests ok')\n", encoding="utf-8")
    return argparse.Namespace(
        agent=agent,
        model=model,
        effort=effort,
        validation_command=f"{sys.executable} {test_script}",
        extensions=None,
        globs=None,
        targets=targets,
        paths=paths,
        scope_instruction=scope_instruction,
        timeout=None,
        refactoring_prompt=None,
        fix_prompt=None,
        show_agent_logs=False,
        show_command_logs=False,
        repo_root=repo_root,
        use_branch=None,
    )


def _env_setup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[Path, Path]:
    """Set up isolated TMPDIR/XDG_DATA_HOME. Returns (tmpdir_root, xdg_root)."""
    tmpdir_root = tmp_path / "tmpdir"
    tmpdir_root.mkdir()
    xdg_root = tmp_path / "xdg"
    xdg_root.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmpdir_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))
    return tmpdir_root, xdg_root


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_e2e_init_then_run_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full flow: init project, run-once with fake agent, verify branch/commit/summary."""
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    tmpdir_root, xdg_root = _env_setup(monkeypatch, tmp_path)

    bin_dir = tmp_path / "bin"
    _write_fake_codex(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_CODEX_STDOUT", "chosen_scope: e2e cleanup\n")
    monkeypatch.setenv("FAKE_CODEX_LAST_MESSAGE", "chosen_scope: e2e cleanup\n")
    monkeypatch.setenv("FAKE_CODEX_TOUCH_FILE", "e2e_file.txt")
    monkeypatch.setenv("FAKE_CODEX_TOUCH_CONTENT", "e2e content\n")

    register_project(repo_root)

    args = _make_run_once_args(repo_root)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0

    branch = continuous_refactoring.current_branch(repo_root)
    assert branch.startswith("cr/")

    log_output = subprocess.run(
        ["git", "log", "--oneline"], cwd=repo_root,
        capture_output=True, text=True, check=True,
    ).stdout
    assert "continuous refactor" in log_output

    run_root = tmpdir_root / "continuous-refactoring"
    run_dirs = list(run_root.iterdir())
    assert len(run_dirs) == 1
    summary_path = run_dirs[0] / "summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["final_status"] == "completed"


def test_e2e_init_then_run_with_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run loop with two targets: first fails validation, second succeeds."""
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    tmpdir_root, xdg_root = _env_setup(monkeypatch, tmp_path)

    register_project(repo_root)

    call_count = 0

    def alternating_agent(**kwargs: object) -> CommandCapture:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            rr = Path(str(kwargs.get("repo_root", "")))
            (rr / "good_change.txt").write_text("good\n", encoding="utf-8")
        return _noop_agent(**kwargs)

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
        return _noop_tests(test_command, repo_root, stdout_path, stderr_path)

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
        repo_root=repo_root,
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
        ["git", "log", "--oneline"], cwd=repo_root,
        capture_output=True, text=True, check=True,
    ).stdout
    assert "target-2" in log_output
    assert "target-1" not in log_output


def test_e2e_taste_flows_through(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Custom taste text appears in the agent prompt."""
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    _env_setup(monkeypatch, tmp_path)

    project = register_project(repo_root)
    custom_taste = "- Never use print statements in production code.\n"
    (project.project_dir / "taste.md").write_text(custom_taste, encoding="utf-8")

    captured_prompts: list[str] = []

    def capture_agent(**kwargs: object) -> CommandCapture:
        captured_prompts.append(str(kwargs.get("prompt", "")))
        return _noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", capture_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", _noop_tests)

    args = _make_run_once_args(repo_root)
    continuous_refactoring.run_once(args)

    assert len(captured_prompts) == 1
    assert "Never use print statements in production code" in captured_prompts[0]


def test_e2e_targets_jsonl_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Targets from JSONL file appear in agent prompt."""
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    _env_setup(monkeypatch, tmp_path)

    register_project(repo_root)

    targets_file = tmp_path / "targets.jsonl"
    targets_file.write_text(
        json.dumps({
            "description": "clean up error handling",
            "files": ["src/errors.py", "src/handlers.py"],
            "scoping": "focus on exception translation",
        }) + "\n",
        encoding="utf-8",
    )

    captured_prompts: list[str] = []

    def capture_agent(**kwargs: object) -> CommandCapture:
        captured_prompts.append(str(kwargs.get("prompt", "")))
        return _noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", capture_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", _noop_tests)

    args = _make_run_once_args(repo_root, targets=targets_file, scope_instruction=None)
    continuous_refactoring.run_once(args)

    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    assert "src/errors.py" in prompt
    assert "src/handlers.py" in prompt
    assert "focus on exception translation" in prompt


def test_e2e_uninitialized_project_degraded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run without init -- should succeed using built-in default taste."""
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    _env_setup(monkeypatch, tmp_path)

    # Deliberately do NOT call register_project

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", _noop_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", _noop_tests)

    args = _make_run_once_args(repo_root)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0


def test_e2e_ctrl_c_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Interrupt mid-run produces exit code 130 and artifact logs mention interruption."""
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    tmpdir_root, xdg_root = _env_setup(monkeypatch, tmp_path)

    register_project(repo_root)

    def interrupting_agent(**kwargs: object) -> CommandCapture:
        raise KeyboardInterrupt

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", interrupting_agent)

    args = _make_run_once_args(repo_root)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 130

    captured = capsys.readouterr()
    assert "Artifact logs:" in captured.err

    run_root = tmpdir_root / "continuous-refactoring"
    run_dirs = list(run_root.iterdir())
    assert len(run_dirs) == 1
    summary = json.loads(
        (run_dirs[0] / "summary.json").read_text(encoding="utf-8")
    )
    assert summary["final_status"] == "interrupted"


def test_e2e_without_init_uses_default_taste(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without init, the built-in default taste text appears in the prompt."""
    repo_root = tmp_path / "repo"
    _init_repo(repo_root)
    _env_setup(monkeypatch, tmp_path)

    # No register_project call

    captured_prompts: list[str] = []

    def capture_agent(**kwargs: object) -> CommandCapture:
        captured_prompts.append(str(kwargs.get("prompt", "")))
        return _noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", capture_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", _noop_tests)

    args = _make_run_once_args(repo_root)
    continuous_refactoring.run_once(args)

    assert len(captured_prompts) == 1
    # The built-in default taste includes this text
    builtin_taste = default_taste_text()
    # Verify each line of the default taste appears in the prompt
    for line in builtin_taste.strip().splitlines():
        line = line.strip()
        if line and not line.startswith("-"):
            continue
        if line:
            assert line.lstrip("- ") in captured_prompts[0], (
                f"Default taste line missing from prompt: {line}"
            )
