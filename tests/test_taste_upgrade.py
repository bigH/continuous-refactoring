from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pytest
from conftest import extract_settle_path, init_repo, make_taste_agent_writer

from continuous_refactoring.cli import _handle_taste, build_parser
from continuous_refactoring.config import (
    TASTE_CURRENT_VERSION,
    default_taste_text,
    global_dir,
    register_project,
)


def _upgrade_args(
    *,
    global_: bool = False,
    agent: str | None = "codex",
    model: str | None = "m",
    effort: str | None = "high",
    force: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        global_=global_, interview=False, upgrade=True,
        agent=agent, model=model, effort=effort, force=force,
    )


# ---------------------------------------------------------------------------
# No-op: current taste → agent NOT invoked
# ---------------------------------------------------------------------------


def test_upgrade_noop_on_current_taste(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    init_repo(repo)
    monkeypatch.chdir(repo)
    project = register_project(repo)
    taste_path = project.project_dir / "taste.md"
    taste_path.parent.mkdir(parents=True, exist_ok=True)
    taste_path.write_text(default_taste_text(), encoding="utf-8")

    calls: list[tuple[str, ...]] = []

    def should_not_run(
        agent: str,
        model: str,
        effort: str,
        prompt: str,
        repo_root: Path,
        **_: object,
    ) -> int:
        _ = (prompt, repo_root)
        calls.append((agent, model, effort))
        return 0

    monkeypatch.setattr(
        "continuous_refactoring.cli.run_agent_interactive_until_settled",
        should_not_run,
    )
    _handle_taste(_upgrade_args())

    assert calls == []
    out = capsys.readouterr().out.strip()
    assert "taste already current" in out
    assert "taste --refine" in out


def test_upgrade_noop_on_current_global_taste(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    gdir = global_dir()
    gdir.mkdir(parents=True, exist_ok=True)
    (gdir / "taste.md").write_text(default_taste_text(), encoding="utf-8")

    calls: list[tuple[str, ...]] = []

    def should_not_run(
        agent: str,
        model: str,
        effort: str,
        prompt: str,
        repo_root: Path,
        **_: object,
    ) -> int:
        _ = (prompt, repo_root)
        calls.append((agent, model, effort))
        return 0

    monkeypatch.setattr(
        "continuous_refactoring.cli.run_agent_interactive_until_settled",
        should_not_run,
    )
    _handle_taste(_upgrade_args(global_=True))

    assert calls == []
    out = capsys.readouterr().out.strip()
    assert "taste already current" in out
    assert "taste --refine" in out


# ---------------------------------------------------------------------------
# Forced upgrade: legacy taste (no version header) → agent invoked
# ---------------------------------------------------------------------------


def test_upgrade_forced_on_legacy_taste(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    init_repo(repo)
    monkeypatch.chdir(repo)
    project = register_project(repo)
    taste_path = project.project_dir / "taste.md"
    taste_path.parent.mkdir(parents=True, exist_ok=True)
    taste_path.write_text("- Old taste without version.\n", encoding="utf-8")

    upgraded = f"taste-scoping-version: {TASTE_CURRENT_VERSION}\n\n- Upgraded.\n"
    monkeypatch.setattr(
        "continuous_refactoring.cli.run_agent_interactive_until_settled",
        make_taste_agent_writer(content=upgraded),
    )
    _handle_taste(_upgrade_args())

    assert taste_path.read_text(encoding="utf-8") == upgraded
    out = capsys.readouterr().out.strip()
    assert out == str(taste_path)


def test_upgrade_prompt_mentions_legacy_and_new_dimensions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    init_repo(repo)
    monkeypatch.chdir(repo)
    project = register_project(repo)
    taste_path = project.project_dir / "taste.md"
    taste_path.parent.mkdir(parents=True, exist_ok=True)
    taste_path.write_text("- Legacy rule.\n", encoding="utf-8")

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
        captured["prompt"] = prompt
        content_path.write_text("- upgraded\n", encoding="utf-8")
        settle_path.write_text(
            f"sha256:{hashlib.sha256(b'- upgraded\n').hexdigest()}",
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(
        "continuous_refactoring.cli.run_agent_interactive_until_settled", capture,
    )
    _handle_taste(_upgrade_args())

    prompt = captured["prompt"]
    assert "no version header" in prompt
    assert "legacy" in prompt.lower()
    assert "large-scope decisions" in prompt
    assert "rollout style" in prompt
    assert f"taste-scoping-version: {TASTE_CURRENT_VERSION}" in prompt
    assert "Legacy rule" in prompt
    assert "Taste settle target" in prompt
    assert extract_settle_path(prompt) == taste_path.with_name("taste.md.done")


# ---------------------------------------------------------------------------
# Agent flags validation
# ---------------------------------------------------------------------------


def test_upgrade_requires_agent_flags_when_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    init_repo(repo)
    monkeypatch.chdir(repo)
    project = register_project(repo)
    taste_path = project.project_dir / "taste.md"
    taste_path.parent.mkdir(parents=True, exist_ok=True)
    taste_path.write_text("- Legacy.\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        _handle_taste(_upgrade_args(agent=None, model=None, effort=None))

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "--upgrade requires" in err


def test_upgrade_requires_agent_flags_when_global_taste_is_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    taste_path = global_dir() / "taste.md"
    taste_path.parent.mkdir(parents=True, exist_ok=True)
    taste_path.write_text("- Legacy.\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        _handle_taste(
            _upgrade_args(global_=True, agent=None, model=None, effort=None),
        )

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "--upgrade requires" in err


def test_upgrade_noop_skips_agent_flag_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    init_repo(repo)
    monkeypatch.chdir(repo)
    project = register_project(repo)
    taste_path = project.project_dir / "taste.md"
    taste_path.parent.mkdir(parents=True, exist_ok=True)
    taste_path.write_text(default_taste_text(), encoding="utf-8")

    _handle_taste(_upgrade_args(agent=None, model=None, effort=None))

    out = capsys.readouterr().out.strip()
    assert "taste already current" in out
    assert "taste --refine" in out


def test_upgrade_rejects_force(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    with pytest.raises(SystemExit) as exc_info:
        _handle_taste(_upgrade_args(force=True))

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "--force requires --interview" in err


# ---------------------------------------------------------------------------
# Argparse: mutual exclusion
# ---------------------------------------------------------------------------


def test_taste_subparser_accepts_upgrade_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(
        ["taste", "--upgrade", "--with", "codex", "--model", "m", "--effort", "high"],
    )
    assert args.upgrade is True
    assert args.interview is False
    assert args.agent == "codex"


def test_taste_interview_and_upgrade_mutually_exclusive() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["taste", "--interview", "--upgrade"])
    assert exc_info.value.code == 2
