from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from collections.abc import Callable

import pytest

from continuous_refactoring.cli import _handle_taste, build_parser
from continuous_refactoring.config import (
    default_taste_text,
    global_dir,
    register_project,
)


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
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
        ["git", "add", "README.md"], cwd=path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True,
    )


def _init_test_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)
    return repo


def _init_taste_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = _init_test_repo(tmp_path, monkeypatch)
    monkeypatch.chdir(repo)
    project = register_project(repo)
    taste_path = project.project_dir / "taste.md"
    taste_path.parent.mkdir(parents=True, exist_ok=True)
    return taste_path


def _interview_args(
    *, global_: bool = False, force: bool = False,
    agent: str | None = "codex", model: str | None = "m", effort: str | None = "high",
) -> argparse.Namespace:
    return argparse.Namespace(
        global_=global_, interview=True, agent=agent, model=model,
        effort=effort, force=force,
    )


def _fake_writer(content: str) -> Callable[..., int]:
    def fake(agent: str, model: str, effort: str, prompt: str, repo_root: Path) -> int:
        taste_path = _extract_taste_path(prompt)
        taste_path.write_text(content, encoding="utf-8")
        return 0
    return fake


def _extract_taste_path(prompt: str) -> Path:
    for line in prompt.splitlines():
        if line.startswith("Taste file target:"):
            return Path(line.split(":", 1)[1].strip())
    raise AssertionError("Taste file target missing from prompt")


# ---------------------------------------------------------------------------
# Flag validation
# ---------------------------------------------------------------------------


def test_interview_requires_agent_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    args = _interview_args(agent=None, model=None, effort=None)
    with pytest.raises(SystemExit) as exc_info:
        _handle_taste(args)
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "--interview requires" in err


def test_interview_rejects_agent_flags_without_interview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    args = argparse.Namespace(
        global_=False, interview=False,
        agent="codex", model="m", effort="high", force=False,
    )
    with pytest.raises(SystemExit) as exc_info:
        _handle_taste(args)
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "require --interview" in err


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def test_interview_writes_taste_project_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    taste_path = _init_taste_project(tmp_path, monkeypatch)

    monkeypatch.setattr(
        "continuous_refactoring.cli.run_agent_interactive",
        _fake_writer("- custom rule\n"),
    )
    _handle_taste(_interview_args())

    assert taste_path.read_text(encoding="utf-8") == "- custom rule\n"
    out = capsys.readouterr().out.strip()
    assert out == str(taste_path)


def test_interview_writes_taste_global(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    expected = global_dir() / "taste.md"

    monkeypatch.setattr(
        "continuous_refactoring.cli.run_agent_interactive",
        _fake_writer("- global rule\n"),
    )
    _handle_taste(_interview_args(global_=True))

    assert expected.read_text(encoding="utf-8") == "- global rule\n"
    out = capsys.readouterr().out.strip()
    assert out == str(expected)


# ---------------------------------------------------------------------------
# Overwrite policy
# ---------------------------------------------------------------------------


def test_interview_refuses_overwrite_without_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    taste_path = _init_taste_project(tmp_path, monkeypatch)
    taste_path.write_text("- pre-existing custom\n", encoding="utf-8")

    calls: list[tuple[str, ...]] = []

    def should_not_run(
        agent: str, model: str, effort: str, prompt: str, repo_root: Path,
    ) -> int:
        calls.append((agent, model, effort))
        return 0

    monkeypatch.setattr(
        "continuous_refactoring.cli.run_agent_interactive", should_not_run,
    )
    with pytest.raises(SystemExit) as exc_info:
        _handle_taste(_interview_args())

    assert exc_info.value.code == 1
    assert calls == []
    assert taste_path.read_text(encoding="utf-8") == "- pre-existing custom\n"
    err = capsys.readouterr().err
    assert "--force" in err


def test_interview_allows_overwrite_on_default_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    taste_path = _init_taste_project(tmp_path, monkeypatch)
    taste_path.write_text(default_taste_text(), encoding="utf-8")

    monkeypatch.setattr(
        "continuous_refactoring.cli.run_agent_interactive",
        _fake_writer("- overwritten\n"),
    )
    _handle_taste(_interview_args())  # no --force

    assert taste_path.read_text(encoding="utf-8") == "- overwritten\n"
    assert not taste_path.with_name("taste.md.bak").exists()


def test_interview_backup_on_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    taste_path = _init_taste_project(tmp_path, monkeypatch)
    taste_path.write_text("original\n", encoding="utf-8")

    monkeypatch.setattr(
        "continuous_refactoring.cli.run_agent_interactive",
        _fake_writer("- replacement\n"),
    )
    _handle_taste(_interview_args(force=True))

    assert taste_path.read_text(encoding="utf-8") == "- replacement\n"
    backup = taste_path.with_name("taste.md.bak")
    assert backup.read_text(encoding="utf-8") == "original\n"


# ---------------------------------------------------------------------------
# Agent outcome handling
# ---------------------------------------------------------------------------


def test_interview_errors_if_agent_did_not_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    taste_path = _init_taste_project(tmp_path, monkeypatch)
    if taste_path.exists():
        taste_path.unlink()

    def no_write(
        agent: str, model: str, effort: str, prompt: str, repo_root: Path,
    ) -> int:
        return 0

    monkeypatch.setattr(
        "continuous_refactoring.cli.run_agent_interactive", no_write,
    )
    with pytest.raises(SystemExit) as exc_info:
        _handle_taste(_interview_args())

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "did not write" in err


def test_interview_errors_on_agent_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)
    monkeypatch.chdir(repo)
    register_project(repo)

    def fail(
        agent: str, model: str, effort: str, prompt: str, repo_root: Path,
    ) -> int:
        return 42

    monkeypatch.setattr(
        "continuous_refactoring.cli.run_agent_interactive", fail,
    )
    with pytest.raises(SystemExit) as exc_info:
        _handle_taste(_interview_args())

    assert exc_info.value.code == 42
    err = capsys.readouterr().err
    assert "42" in err


# ---------------------------------------------------------------------------
# Prompt composition
# ---------------------------------------------------------------------------


def test_interview_prompt_includes_existing_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)
    monkeypatch.chdir(repo)
    project = register_project(repo)
    taste_path = project.project_dir / "taste.md"
    taste_path.parent.mkdir(parents=True, exist_ok=True)
    existing = "- Prefer deletion.\n- Keep comments rare.\n"
    taste_path.write_text(existing, encoding="utf-8")

    captured: dict[str, str] = {}

    def capture(
        agent: str, model: str, effort: str, prompt: str, repo_root: Path,
    ) -> int:
        captured["prompt"] = prompt
        Path(_extract_taste_path(prompt)).write_text("- new\n", encoding="utf-8")
        return 0

    monkeypatch.setattr(
        "continuous_refactoring.cli.run_agent_interactive", capture,
    )
    _handle_taste(_interview_args(force=True))

    prompt = captured["prompt"]
    assert "Existing taste content" in prompt
    assert "starting draft" in prompt
    assert existing.strip() in prompt


# ---------------------------------------------------------------------------
# Argparse-level validation sanity (covers the subparser wiring itself)
# ---------------------------------------------------------------------------


def test_taste_subparser_accepts_interview_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "taste", "--interview", "--with", "codex",
            "--model", "gpt-x", "--effort", "xhigh", "--force",
        ]
    )
    assert args.interview is True
    assert args.agent == "codex"
    assert args.model == "gpt-x"
    assert args.effort == "xhigh"
    assert args.force is True
