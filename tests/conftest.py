from __future__ import annotations

import argparse
import hashlib
from collections.abc import Callable
import sys
from pathlib import Path

import pytest

import continuous_refactoring
import continuous_refactoring.loop
from continuous_refactoring.artifacts import CommandCapture
from continuous_refactoring.config import register_project


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


def _extract_prompt_field(prompt: str, label: str) -> Path:
    prefix = f"{label}:"
    for line in prompt.splitlines():
        if line.startswith(prefix):
            return Path(line.split(":", 1)[1].strip())
    raise AssertionError(f"{label} missing from prompt")


def extract_taste_path(prompt: str) -> Path:
    return _extract_prompt_field(prompt, "Taste file target")


def extract_settle_path(prompt: str) -> Path:
    return _extract_prompt_field(prompt, "Taste settle target")


def make_taste_agent_writer(
    *,
    content: str | None = None,
    return_code: int = 0,
    captured: dict[str, str] | None = None,
) -> Callable[..., int]:
    def fake(
        agent: str,
        model: str,
        effort: str,
        prompt: str,
        repo_root: Path,
        *,
        content_path: Path,
        settle_path: Path,
        settle_window_seconds: float = 2.0,
        poll_interval_seconds: float = 0.1,
    ) -> int:
        taste_path = extract_taste_path(prompt)
        assert content_path == taste_path
        assert settle_path == extract_settle_path(prompt)
        if captured is not None:
            captured["prompt"] = prompt
        if content is None:
            return return_code
        taste_path.write_text(content, encoding="utf-8")
        settle_path.write_text(
            f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}",
            encoding="utf-8",
        )
        return return_code

    return fake


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


def init_taste_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    init_repo(repo)
    monkeypatch.chdir(repo)
    project = register_project(repo)
    taste_path = project.project_dir / "taste.md"
    taste_path.parent.mkdir(parents=True, exist_ok=True)
    return taste_path


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


def _record_command(
    *,
    returncode: int,
    stdout: str,
    stderr: str,
    stdout_path: Path,
    stderr_path: Path,
    command: tuple[str, ...] = ("pytest",),
) -> CommandCapture:
    for path, content in ((stdout_path, stdout), (stderr_path, stderr)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return CommandCapture(
        command=command,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )


def noop_agent(**kwargs: object) -> CommandCapture:
    return _record_command(
        returncode=0,
        stdout="noop\n",
        stderr="",
        command=("fake",),
        stdout_path=kwargs["stdout_path"],  # type: ignore[arg-type]
        stderr_path=kwargs["stderr_path"],  # type: ignore[arg-type]
    )


def noop_tests(
    test_command: str,
    repo_root: Path,
    stdout_path: Path,
    stderr_path: Path,
    **kwargs: object,
) -> CommandCapture:
    return _record_command(
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
    return _record_command(
        returncode=1,
        stdout="FAILED\n",
        stderr="",
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )


def _default_validation_command(repo_root: Path) -> str:
    test_script = repo_root.parent / "check_tests.py"
    if not test_script.exists():
        test_script.write_text("print('tests ok')\n", encoding="utf-8")
    return f"{sys.executable} {test_script}"


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
    if validation_command is None:
        validation_command = _default_validation_command(repo_root)
    return argparse.Namespace(
        agent=agent,
        model=model,
        effort=effort,
        validation_command=validation_command,
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


def make_run_loop_args(
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
    sleep: float = 0.0,
    use_branch: str | None = None,
    show_agent_logs: bool = False,
    show_command_logs: bool = False,
    focus_on_live_migrations: bool = False,
) -> argparse.Namespace:
    if validation_command is None:
        validation_command = _default_validation_command(repo_root)

    return argparse.Namespace(
        agent=agent,
        model=model,
        effort=effort,
        validation_command=validation_command,
        extensions=extensions,
        globs=globs,
        targets=targets,
        paths=paths,
        scope_instruction=scope_instruction,
        timeout=timeout,
        refactoring_prompt=refactoring_prompt,
        fix_prompt=fix_prompt,
        show_agent_logs=show_agent_logs,
        show_command_logs=show_command_logs,
        repo_root=repo_root,
        max_attempts=max_attempts,
        max_refactors=max_refactors,
        no_push=no_push,
        push_remote=push_remote,
        commit_message_prefix=commit_message_prefix,
        max_consecutive_failures=max_consecutive_failures,
        sleep=sleep,
        use_branch=use_branch,
        focus_on_live_migrations=focus_on_live_migrations,
    )


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _prepare_run_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    (tmp_path / "tmpdir").mkdir()
    (tmp_path / "xdg").mkdir()
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmpdir"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    return repo_root


@pytest.fixture
def run_once_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return _prepare_run_env(tmp_path, monkeypatch)


@pytest.fixture
def run_loop_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return _prepare_run_env(tmp_path, monkeypatch)


@pytest.fixture
def prompt_capture(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    prompts: list[str] = []

    def capture_agent(**kwargs: object) -> CommandCapture:
        prompts.append(str(kwargs.get("prompt", "")))
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", capture_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)
    return prompts
