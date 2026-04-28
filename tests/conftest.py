from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest

import continuous_refactoring
import continuous_refactoring.loop
from continuous_refactoring.artifacts import CommandCapture
from continuous_refactoring.config import (
    ProjectEntry,
    app_data_dir,
    load_manifest,
    register_project,
)
from continuous_refactoring.effort import (
    DEFAULT_EFFORT,
    DEFAULT_MAX_ALLOWED_EFFORT,
)


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


def assert_single_prompt(prompt_capture: list[str], *needles: str) -> str:
    assert len(prompt_capture) == 1
    prompt = prompt_capture[0]
    for needle in needles:
        assert needle in prompt
    return prompt


def patch_classifier_trap(
    monkeypatch: pytest.MonkeyPatch,
    message: str = "classify_target must not be called",
) -> None:
    def trap(*_args: object, **_kwargs: object) -> object:
        raise AssertionError(message)

    monkeypatch.setattr("continuous_refactoring.routing_pipeline.classify_target", trap)


def _single_run_artifact_dir(repo_root: Path) -> Path:
    run_root = repo_root.parent / "tmpdir" / "continuous-refactoring"
    run_dirs = list(run_root.iterdir())
    assert len(run_dirs) == 1
    return run_dirs[0]


def read_single_run_summary(repo_root: Path) -> dict[str, object]:
    return json.loads(
        (_single_run_artifact_dir(repo_root) / "summary.json").read_text(
            encoding="utf-8"
        )
    )


def read_single_run_events(repo_root: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (_single_run_artifact_dir(repo_root) / "events.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]


def assert_single_run_final_status(repo_root: Path, expected_status: str) -> None:
    summary = read_single_run_summary(repo_root)
    assert summary["final_status"] == expected_status


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
        assert content_path == extract_taste_path(prompt)
        assert settle_path == extract_settle_path(prompt)
        if captured is not None:
            captured["prompt"] = prompt
            captured["content_path"] = str(content_path)
            captured["settle_path"] = str(settle_path)
        if content is None:
            return return_code
        content_path.write_text(content, encoding="utf-8")
        settle_path.write_text(
            f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}",
            encoding="utf-8",
        )
        return return_code

    return fake


def make_taste_args(
    mode: Literal["plain", "interview", "upgrade", "refine"] = "plain",
    *,
    global_: bool = False,
    agent: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    force: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        global_=global_,
        interview=mode == "interview",
        upgrade=mode == "upgrade",
        refine=mode == "refine",
        agent=agent,
        model=model,
        effort=effort,
        force=force,
    )


@dataclass(frozen=True)
class RegisteredProjectLayout:
    entry: ProjectEntry
    project_dir: Path
    taste_path: Path


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


def init_repo_with_temp_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, repo_name: str = "project"
) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / repo_name
    init_repo(repo)
    return repo


def init_taste_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    init_repo(repo)
    monkeypatch.chdir(repo)
    project = register_project(repo)
    taste_path = project.project_dir / "taste.md"
    taste_path.parent.mkdir(parents=True, exist_ok=True)
    return taste_path


def load_single_registered_project() -> RegisteredProjectLayout:
    manifest = load_manifest()
    assert len(manifest) == 1
    entry = next(iter(manifest.values()))
    project_dir = app_data_dir() / "projects" / entry.uuid
    return RegisteredProjectLayout(
        entry=entry,
        project_dir=project_dir,
        taste_path=project_dir / "taste.md",
    )


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


def touch_file_agent(relative_path: str, content: str = "x\n") -> Callable[..., CommandCapture]:
    def fake(**kwargs: object) -> CommandCapture:
        repo_root = Path(str(kwargs.get("repo_root", "")))
        destination = repo_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        return noop_agent(**kwargs)

    return fake


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


def _build_run_args(
    repo_root: Path,
    *,
    agent: str,
    model: str,
    effort: str,
    default_effort: str | None,
    max_allowed_effort: str | None,
    validation_command: str | None,
    scope_instruction: str | None,
    timeout: int | None,
    refactoring_prompt: Path | None,
    extensions: str | None,
    globs: str | None,
    targets: Path | None,
    paths: str | None,
) -> dict[str, object]:
    if validation_command is None:
        validation_command = _default_validation_command(repo_root)
    resolved_default_effort = default_effort or effort
    resolved_max_allowed_effort = max_allowed_effort or DEFAULT_MAX_ALLOWED_EFFORT
    return {
        "agent": agent,
        "model": model,
        "effort": resolved_default_effort,
        "default_effort": resolved_default_effort,
        "max_allowed_effort": resolved_max_allowed_effort,
        "validation_command": validation_command,
        "extensions": extensions,
        "globs": globs,
        "targets": targets,
        "paths": paths,
        "scope_instruction": scope_instruction,
        "timeout": timeout,
        "refactoring_prompt": refactoring_prompt,
        "show_agent_logs": False,
        "show_command_logs": False,
        "repo_root": repo_root,
    }


def make_run_once_args(
    repo_root: Path,
    *,
    agent: str = "codex",
    model: str = "fake-model",
    effort: str = DEFAULT_EFFORT,
    default_effort: str | None = None,
    max_allowed_effort: str | None = None,
    validation_command: str | None = None,
    scope_instruction: str | None = "general cleanup",
    timeout: int | None = None,
    refactoring_prompt: Path | None = None,
    extensions: str | None = None,
    globs: str | None = None,
    targets: Path | None = None,
    paths: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        **_build_run_args(
            repo_root=repo_root,
            agent=agent,
            model=model,
            effort=effort,
            default_effort=default_effort,
            max_allowed_effort=max_allowed_effort,
            validation_command=validation_command,
            scope_instruction=scope_instruction,
            timeout=timeout,
            refactoring_prompt=refactoring_prompt,
            extensions=extensions,
            globs=globs,
            targets=targets,
            paths=paths,
        ),
        fix_prompt=None,
    )


def make_run_loop_args(
    repo_root: Path,
    *,
    agent: str = "codex",
    model: str = "fake-model",
    effort: str = DEFAULT_EFFORT,
    default_effort: str | None = None,
    max_allowed_effort: str | None = None,
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
    commit_message_prefix: str = "continuous refactor",
    max_consecutive_failures: int = 3,
    sleep: float = 0.0,
    show_agent_logs: bool = False,
    show_command_logs: bool = False,
    focus_on_live_migrations: bool = False,
) -> argparse.Namespace:
    args = _build_run_args(
        repo_root=repo_root,
        agent=agent,
        model=model,
        effort=effort,
        default_effort=default_effort,
        max_allowed_effort=max_allowed_effort,
        validation_command=validation_command,
        scope_instruction=scope_instruction,
        timeout=timeout,
        refactoring_prompt=refactoring_prompt,
        extensions=extensions,
        globs=globs,
        targets=targets,
        paths=paths,
    )
    args.update(
        {
            "fix_prompt": fix_prompt,
            "show_agent_logs": show_agent_logs,
            "show_command_logs": show_command_logs,
            "max_attempts": max_attempts,
            "max_refactors": max_refactors,
            "commit_message_prefix": commit_message_prefix,
            "max_consecutive_failures": max_consecutive_failures,
            "sleep": sleep,
            "focus_on_live_migrations": focus_on_live_migrations,
        }
    )
    return argparse.Namespace(**args)


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
