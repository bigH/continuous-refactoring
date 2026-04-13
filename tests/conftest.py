from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

import continuous_refactoring
import continuous_refactoring.loop
from continuous_refactoring.artifacts import CommandCapture


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


def init_repo(path: Path) -> None:
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


def write_fake_codex(bin_dir: Path) -> Path:
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


def noop_agent(**kwargs: object) -> CommandCapture:
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


def noop_tests(
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


def failing_tests(
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


def make_run_once_args(
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


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def run_once_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    (tmp_path / "tmpdir").mkdir()
    (tmp_path / "xdg").mkdir()
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmpdir"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    return repo_root


@pytest.fixture
def prompt_capture(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    prompts: list[str] = []

    def capture_agent(**kwargs: object) -> CommandCapture:
        prompts.append(str(kwargs.get("prompt", "")))
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", capture_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)
    return prompts
