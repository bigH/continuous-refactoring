from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

import continuous_refactoring
import continuous_refactoring.loop
from continuous_refactoring.artifacts import CommandCapture
from continuous_refactoring.config import load_taste
from continuous_refactoring.prompts import DEFAULT_REFACTORING_PROMPT, compose_full_prompt
from continuous_refactoring.targeting import Target, resolve_targets

from conftest import (
    init_repo,
    make_run_once_args,
    noop_agent,
    noop_tests,
)


def _classifier_trap(*_args: object, **_kwargs: object) -> object:
    raise AssertionError(
        "classify_target must not be called when live-migrations-dir is unset"
    )


def _expected_one_shot_prompt(
    repo_root: Path,
    validation_command: str,
    scope_instruction: str = "general cleanup",
) -> str:
    taste = load_taste(None)
    targets = resolve_targets(
        extensions=None, globs=None, targets_path=None, paths=None,
        repo_root=repo_root,
    )
    target = (
        targets[0]
        if targets
        else Target(
            description="general refactoring",
            files=(),
            scoping=scope_instruction,
        )
    )
    return compose_full_prompt(
        base_prompt=DEFAULT_REFACTORING_PROMPT,
        taste=taste,
        target=target,
        scope_instruction=scope_instruction,
        validation_command=validation_command,
        attempt=1,
    )


def _make_run_loop_args(
    repo_root: Path,
    *,
    targets: Path | None = None,
    max_refactors: int | None = None,
    no_push: bool = True,
    push_remote: str = "origin",
    commit_message_prefix: str = "continuous refactor",
    max_consecutive_failures: int = 3,
) -> argparse.Namespace:
    test_script = repo_root.parent / "check_tests.py"
    if not test_script.exists():
        test_script.write_text("print('tests ok')\n", encoding="utf-8")
    return argparse.Namespace(
        agent="codex",
        model="fake-model",
        effort="xhigh",
        validation_command=f"{sys.executable} {test_script}",
        extensions=None,
        globs=None,
        targets=targets,
        paths=None,
        scope_instruction="general cleanup",
        timeout=None,
        refactoring_prompt=None,
        fix_prompt=None,
        show_agent_logs=False,
        show_command_logs=False,
        repo_root=repo_root,
        max_attempts=None,
        max_refactors=max_refactors,
        no_push=no_push,
        push_remote=push_remote,
        commit_message_prefix=commit_message_prefix,
        max_consecutive_failures=max_consecutive_failures,
        use_branch=None,
    )


# ---------------------------------------------------------------------------
# Case A: run_once prompt equals compose_full_prompt with same inputs
# ---------------------------------------------------------------------------


def test_run_once_prompt_matches_compose_full_prompt(
    run_once_env: Path,
    prompt_capture: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "continuous_refactoring.loop.classify_target", _classifier_trap,
    )
    args = make_run_once_args(run_once_env)
    continuous_refactoring.run_once(args)

    assert len(prompt_capture) == 1
    expected = _expected_one_shot_prompt(run_once_env, args.validation_command)
    assert prompt_capture[0] == expected


# ---------------------------------------------------------------------------
# Case B: run_once branch pattern + "Branch: cr/" output
# ---------------------------------------------------------------------------


def test_run_once_branch_and_output_unchanged(
    run_once_env: Path,
    prompt_capture: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "continuous_refactoring.loop.classify_target", _classifier_trap,
    )
    args = make_run_once_args(run_once_env)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0
    branch = continuous_refactoring.current_branch(run_once_env)
    assert re.match(r"^cr/\d{8}T\d{6}$", branch)
    assert "Branch: cr/" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Case C: run_loop 2-target batch — invocations, commit prefix, push
# ---------------------------------------------------------------------------


def test_run_loop_two_targets_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    (tmp_path / "tmpdir").mkdir()
    (tmp_path / "xdg").mkdir()
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmpdir"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(
        "continuous_refactoring.loop.classify_target", _classifier_trap,
    )

    agent_calls: list[str] = []
    push_calls: list[tuple[str, str]] = []

    def tracking_agent(**kwargs: object) -> CommandCapture:
        agent_calls.append(str(kwargs.get("prompt", "")))
        rr = Path(str(kwargs.get("repo_root", "")))
        (rr / f"change{len(agent_calls)}.txt").write_text("x\n", encoding="utf-8")
        return noop_agent(**kwargs)

    def tracking_push(repo_root: Path, remote: str, branch: str) -> None:
        push_calls.append((remote, branch))

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", tracking_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)
    monkeypatch.setattr("continuous_refactoring.loop.git_push", tracking_push)

    targets_file = tmp_path / "targets.jsonl"
    lines = [
        json.dumps({"description": "target-0", "files": ["a.py"]}),
        json.dumps({"description": "target-1", "files": ["b.py"]}),
    ]
    targets_file.write_text("\n".join(lines), encoding="utf-8")

    args = _make_run_loop_args(
        repo_root,
        targets=targets_file,
        no_push=False,
        commit_message_prefix="continuous refactor",
    )
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    assert len(agent_calls) == 2
    assert len(push_calls) == 2

    log = continuous_refactoring.run_command(
        ["git", "log", "--oneline"], cwd=repo_root,
    ).stdout
    assert "continuous refactor: target-0" in log
    assert "continuous refactor: target-1" in log


# ---------------------------------------------------------------------------
# Case D: live-migrations-dir + cohesive-cleanup = same one-shot path
# ---------------------------------------------------------------------------


def test_cohesive_cleanup_matches_one_shot(
    run_once_env: Path,
    prompt_capture: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    live_dir = run_once_env / ".migrations"
    live_dir.mkdir()

    classify_calls: list[int] = []

    def stub_classifier(*_args: object, **_kwargs: object) -> str:
        classify_calls.append(1)
        return "cohesive-cleanup"

    monkeypatch.setattr(
        "continuous_refactoring.loop._resolve_live_migrations_dir",
        lambda _repo_root: live_dir,
    )
    monkeypatch.setattr(
        "continuous_refactoring.loop.classify_target", stub_classifier,
    )

    args = make_run_once_args(run_once_env)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0
    assert len(classify_calls) == 1

    assert len(prompt_capture) == 1
    expected = _expected_one_shot_prompt(run_once_env, args.validation_command)
    assert prompt_capture[0] == expected

    branch = continuous_refactoring.current_branch(run_once_env)
    assert re.match(r"^cr/\d{8}T\d{6}$", branch)
    assert "Branch: cr/" in capsys.readouterr().out
