from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from conftest import init_taste_project, make_taste_agent_writer

from continuous_refactoring.cli import _handle_taste, build_parser
from continuous_refactoring.config import default_taste_text, global_dir


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


@pytest.mark.parametrize(
    ("global_", "existing", "expected"),
    [
        (False, "- keep names honest\n", "- keep names honest\n- delete dead branches fast\n"),
        (True, "- keep tests readable\n", "- keep tests readable\n- use mocks sparingly\n"),
    ],
)
def test_refine_writes_existing_taste_in_place(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    global_: bool,
    existing: str,
    expected: str,
) -> None:
    if global_:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
        taste_path = global_dir() / "taste.md"
        taste_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        taste_path = init_taste_project(tmp_path, monkeypatch)

    taste_path.write_text(existing, encoding="utf-8")

    monkeypatch.setattr(
        "continuous_refactoring.cli.run_agent_interactive_until_settled",
        make_taste_agent_writer(content=expected),
    )
    _handle_taste(_refine_args(global_=global_))

    assert taste_path.read_text(encoding="utf-8") == expected
    assert not taste_path.with_name("taste.md.done").exists()
    assert not taste_path.with_name("taste.md.bak").exists()
    out = capsys.readouterr().out.strip()
    assert out == str(taste_path)


def test_refine_uses_default_taste_as_starting_draft_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    taste_path = init_taste_project(tmp_path, monkeypatch)
    if taste_path.exists():
        taste_path.unlink()

    captured: dict[str, str] = {}
    monkeypatch.setattr(
        "continuous_refactoring.cli.run_agent_interactive_until_settled",
        make_taste_agent_writer(content="- refined from default\n", captured=captured),
    )
    _handle_taste(_refine_args())

    prompt = captured["prompt"]
    assert "Starting draft" in prompt
    assert default_taste_text().strip() in prompt


def test_refine_prompt_allows_open_ended_improvement_and_explicit_write_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    taste_path = init_taste_project(tmp_path, monkeypatch)
    taste_path.write_text("- Keep helpers honest.\n", encoding="utf-8")

    captured: dict[str, str] = {}
    monkeypatch.setattr(
        "continuous_refactoring.cli.run_agent_interactive_until_settled",
        make_taste_agent_writer(content="- refined\n", captured=captured),
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
    assert captured["content_path"] == str(taste_path)
    assert captured["settle_path"] == str(taste_path.with_name("taste.md.done"))


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
