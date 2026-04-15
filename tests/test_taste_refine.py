from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

from continuous_refactoring.cli import _handle_taste, build_parser
from continuous_refactoring.config import default_taste_text, global_dir, register_project


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    (path / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=path,
        check=True,
        capture_output=True,
    )


def _init_taste_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)
    monkeypatch.chdir(repo)
    project = register_project(repo)
    taste_path = project.project_dir / "taste.md"
    taste_path.parent.mkdir(parents=True, exist_ok=True)
    return taste_path


def _refine_args(
    *,
    global_: bool = False,
    agent: str | None = "codex",
    model: str | None = "m",
    effort: str | None = "high",
    force: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        global_=global_,
        interview=False,
        upgrade=False,
        refine=True,
        agent=agent,
        model=model,
        effort=effort,
        force=force,
    )


def _extract_taste_path(prompt: str) -> Path:
    return Path(_extract_prompt_field(prompt, "Taste file target"))


def _extract_settle_path(prompt: str) -> Path:
    return Path(_extract_prompt_field(prompt, "Taste settle target"))


def _extract_prompt_field(prompt: str, label: str) -> str:
    prefix = f"{label}:"
    for line in prompt.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    raise AssertionError(f"{label} missing from prompt")


def _fake_refine_writer(
    content: str,
    *,
    capture: dict[str, str] | None = None,
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
        taste_path = _extract_taste_path(prompt)
        assert content_path == taste_path
        assert settle_path == _extract_settle_path(prompt)
        if capture is not None:
            capture["prompt"] = prompt
        _ = (
            agent,
            model,
            effort,
            repo_root,
            settle_window_seconds,
            poll_interval_seconds,
        )
        taste_path.write_text(content, encoding="utf-8")
        settle_path.write_text(
            f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}",
            encoding="utf-8",
        )
        return 0

    return fake


def test_refine_requires_agent_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    args = _refine_args(agent=None, model=None, effort=None)

    with pytest.raises(SystemExit) as exc_info:
        _handle_taste(args)

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "--refine requires" in err


def test_refine_rejects_force(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    with pytest.raises(SystemExit) as exc_info:
        _handle_taste(_refine_args(force=True))

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "--force requires --interview" in err


def test_refine_writes_existing_project_taste_in_place(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    taste_path = _init_taste_project(tmp_path, monkeypatch)
    taste_path.write_text("- keep names honest\n", encoding="utf-8")

    monkeypatch.setattr(
        "continuous_refactoring.cli.run_agent_interactive_until_settled",
        _fake_refine_writer("- keep names honest\n- delete dead branches fast\n"),
    )
    _handle_taste(_refine_args())

    assert (
        taste_path.read_text(encoding="utf-8")
        == "- keep names honest\n- delete dead branches fast\n"
    )
    assert not taste_path.with_name("taste.md.done").exists()
    assert not taste_path.with_name("taste.md.bak").exists()
    out = capsys.readouterr().out.strip()
    assert out == str(taste_path)


def test_refine_writes_existing_global_taste_in_place(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    taste_path = global_dir() / "taste.md"
    taste_path.parent.mkdir(parents=True, exist_ok=True)
    taste_path.write_text("- keep tests readable\n", encoding="utf-8")

    monkeypatch.setattr(
        "continuous_refactoring.cli.run_agent_interactive_until_settled",
        _fake_refine_writer("- keep tests readable\n- use mocks sparingly\n"),
    )
    _handle_taste(_refine_args(global_=True))

    assert (
        taste_path.read_text(encoding="utf-8")
        == "- keep tests readable\n- use mocks sparingly\n"
    )
    assert not taste_path.with_name("taste.md.done").exists()
    assert not taste_path.with_name("taste.md.bak").exists()
    out = capsys.readouterr().out.strip()
    assert out == str(taste_path)


def test_refine_uses_default_taste_as_starting_draft_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    taste_path = _init_taste_project(tmp_path, monkeypatch)
    if taste_path.exists():
        taste_path.unlink()

    captured: dict[str, str] = {}

    def capture(
        agent: str,
        model: str,
        effort: str,
        prompt: str,
        repo_root: Path,
        *,
        content_path: Path,
        settle_path: Path,
        **_: object,
    ) -> int:
        _ = (agent, model, effort, repo_root)
        assert content_path.exists() is False
        captured["prompt"] = prompt
        content_path.write_text("- refined from default\n", encoding="utf-8")
        settle_path.write_text(
            f"sha256:{hashlib.sha256(b'- refined from default\n').hexdigest()}",
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(
        "continuous_refactoring.cli.run_agent_interactive_until_settled",
        capture,
    )
    _handle_taste(_refine_args())

    prompt = captured["prompt"]
    assert "Starting draft" in prompt
    assert default_taste_text().strip() in prompt


def test_refine_prompt_allows_open_ended_improvement_and_explicit_write_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    taste_path = _init_taste_project(tmp_path, monkeypatch)
    taste_path.write_text("- Keep helpers honest.\n", encoding="utf-8")

    captured: dict[str, str] = {}
    monkeypatch.setattr(
        "continuous_refactoring.cli.run_agent_interactive_until_settled",
        _fake_refine_writer("- refined\n", capture=captured),
    )
    _handle_taste(_refine_args())

    prompt = captured["prompt"]
    assert "improve the taste doc however they like" in prompt
    assert "let you know when they want you to write the file" in prompt
    assert "session will be automatically ended" in prompt
    assert "Wait to write until the user explicitly tells you to write the file" in prompt
    assert "compute its SHA-256 and write exactly" in prompt
    assert "do not modify either file again" in prompt
    assert "Do not add one unless the user explicitly asks for it" in prompt
    assert "- Keep helpers honest." in prompt
    assert _extract_settle_path(prompt) == taste_path.with_name("taste.md.done")


def test_taste_subparser_accepts_refine_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(
        ["taste", "--refine", "--with", "codex", "--model", "gpt-x", "--effort", "xhigh"],
    )

    assert args.refine is True
    assert args.interview is False
    assert args.upgrade is False
    assert args.agent == "codex"
    assert args.model == "gpt-x"
    assert args.effort == "xhigh"


@pytest.mark.parametrize("other_mode", ["--interview", "--upgrade"])
def test_taste_refine_is_mutually_exclusive_with_interview_and_upgrade(
    other_mode: str,
) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["taste", "--refine", other_mode])

    assert exc_info.value.code == 2
