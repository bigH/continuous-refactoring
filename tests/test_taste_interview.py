from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from conftest import (
    extract_settle_path,
    init_repo,
    init_repo_with_temp_home,
    init_taste_project,
    make_taste_args,
    make_taste_agent_writer,
)

from continuous_refactoring.cli import _handle_taste, build_parser
from continuous_refactoring.config import (
    DEFAULT_REPO_TASTE_PATH,
    default_taste_text,
    global_dir,
    register_project,
    set_repo_taste_path,
)

_AGENT_RUNNER_PATH = "continuous_refactoring.cli.run_agent_interactive_until_settled"


def _interview_args(
    *,
    global_: bool = False,
    force: bool = False,
    agent: str | None = "codex",
    model: str | None = "m",
    effort: str | None = "high",
) -> argparse.Namespace:
    return make_taste_args(
        "interview",
        global_=global_,
        force=force,
        agent=agent,
        model=model,
        effort=effort,
    )


def _fail_if_taste_agent_runs(**_: object) -> int:
    pytest.fail("taste agent should not be invoked")


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
    with pytest.raises(SystemExit) as exc_info:
        _handle_taste(make_taste_args(agent="codex", model="m", effort="high"))
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "require --interview, --upgrade, or --refine" in err


def test_force_requires_interview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    with pytest.raises(SystemExit) as exc_info:
        _handle_taste(make_taste_args(force=True))

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "--force requires --interview" in err


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def test_interview_writes_taste_project_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    taste_path = init_taste_project(tmp_path, monkeypatch)

    monkeypatch.setattr(
        _AGENT_RUNNER_PATH,
        make_taste_agent_writer(content="- custom rule\n"),
    )
    _handle_taste(_interview_args())

    assert taste_path.read_text(encoding="utf-8") == "- custom rule\n"
    assert not taste_path.with_name("taste.md.done").exists()
    out = capsys.readouterr().out.strip()
    assert out == str(taste_path)


def test_interview_writes_configured_repo_taste(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    monkeypatch.chdir(repo)
    project = register_project(repo)
    set_repo_taste_path(project.entry.uuid, DEFAULT_REPO_TASTE_PATH)
    taste_path = (repo / DEFAULT_REPO_TASTE_PATH).resolve()

    captured: dict[str, str] = {}
    monkeypatch.setattr(
        _AGENT_RUNNER_PATH,
        make_taste_agent_writer(
            content="- repo custom rule\n",
            captured=captured,
        ),
    )
    _handle_taste(_interview_args())

    assert taste_path.read_text(encoding="utf-8") == "- repo custom rule\n"
    assert captured["content_path"] == str(taste_path)
    assert captured["settle_path"] == str(taste_path.with_name("taste.md.done"))
    out = capsys.readouterr().out.strip()
    assert out == str(taste_path)


def test_interview_writes_taste_global(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    expected = global_dir() / "taste.md"

    monkeypatch.setattr(
        _AGENT_RUNNER_PATH,
        make_taste_agent_writer(content="- global rule\n"),
    )
    _handle_taste(_interview_args(global_=True))

    assert expected.read_text(encoding="utf-8") == "- global rule\n"
    assert not expected.with_name("taste.md.done").exists()
    out = capsys.readouterr().out.strip()
    assert out == str(expected)


# ---------------------------------------------------------------------------
# Overwrite policy
# ---------------------------------------------------------------------------


def test_interview_refuses_overwrite_without_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    taste_path = init_taste_project(tmp_path, monkeypatch)
    taste_path.write_text("- pre-existing custom\n", encoding="utf-8")

    monkeypatch.setattr(_AGENT_RUNNER_PATH, _fail_if_taste_agent_runs)
    with pytest.raises(SystemExit) as exc_info:
        _handle_taste(_interview_args())

    assert exc_info.value.code == 1
    assert taste_path.read_text(encoding="utf-8") == "- pre-existing custom\n"
    err = capsys.readouterr().err
    assert "--force" in err


def test_interview_allows_overwrite_on_default_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    taste_path = init_taste_project(tmp_path, monkeypatch)
    taste_path.write_text(default_taste_text(), encoding="utf-8")

    monkeypatch.setattr(
        _AGENT_RUNNER_PATH,
        make_taste_agent_writer(content="- overwritten\n"),
    )
    _handle_taste(_interview_args())  # no --force

    assert taste_path.read_text(encoding="utf-8") == "- overwritten\n"
    assert not taste_path.with_name("taste.md.bak").exists()


def test_interview_backup_on_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    taste_path = init_taste_project(tmp_path, monkeypatch)
    taste_path.write_text("original\n", encoding="utf-8")

    monkeypatch.setattr(
        _AGENT_RUNNER_PATH,
        make_taste_agent_writer(content="- replacement\n"),
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
    taste_path = init_taste_project(tmp_path, monkeypatch)
    assert not taste_path.exists()

    monkeypatch.setattr(
        _AGENT_RUNNER_PATH,
        make_taste_agent_writer(),
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
    init_repo(repo)
    monkeypatch.chdir(repo)
    register_project(repo)

    monkeypatch.setattr(
        _AGENT_RUNNER_PATH,
        make_taste_agent_writer(return_code=42),
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
    init_repo(repo)
    monkeypatch.chdir(repo)
    project = register_project(repo)
    taste_path = project.project_dir / "taste.md"
    taste_path.parent.mkdir(parents=True, exist_ok=True)
    existing = "- Prefer deletion.\n- Keep comments rare.\n"
    taste_path.write_text(existing, encoding="utf-8")

    captured: dict[str, str] = {}

    monkeypatch.setattr(
        _AGENT_RUNNER_PATH,
        make_taste_agent_writer(content="- new\n", captured=captured),
    )
    _handle_taste(_interview_args(force=True))

    prompt = captured["prompt"]
    assert "Existing taste content" in prompt
    assert "starting draft" in prompt
    assert existing.strip() in prompt
    assert "Taste settle target" in prompt
    assert extract_settle_path(prompt) == taste_path.with_name("taste.md.done")


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
