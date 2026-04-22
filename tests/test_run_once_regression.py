from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

import continuous_refactoring
import continuous_refactoring.loop
from continuous_refactoring.artifacts import CommandCapture
from continuous_refactoring.config import load_taste
from continuous_refactoring.prompts import DEFAULT_REFACTORING_PROMPT, compose_full_prompt
from continuous_refactoring.targeting import resolve_targets

from conftest import (
    init_repo,
    make_run_loop_args,
    make_run_once_args,
    noop_agent,
    noop_tests,
)


def _classifier_trap(*_args: object, **_kwargs: object) -> object:
    raise AssertionError(
        "classify_target must not be called when live-migrations-dir is unset"
    )


def _expected_one_shot_prompt(repo_root: Path, validation_command: str) -> str:
    targets = resolve_targets(
        extensions=None, globs=None, targets_path=None, paths=None,
        repo_root=repo_root,
    )
    return compose_full_prompt(
        base_prompt=DEFAULT_REFACTORING_PROMPT,
        taste=load_taste(None),
        target=targets[0],
        scope_instruction="general cleanup",
        validation_command=validation_command,
        attempt=1,
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
        "continuous_refactoring.routing_pipeline.classify_target", _classifier_trap,
    )
    args = make_run_once_args(run_once_env)
    continuous_refactoring.run_once(args)

    assert len(prompt_capture) == 1
    expected = _expected_one_shot_prompt(run_once_env, args.validation_command)
    assert prompt_capture[0] == expected


def test_run_once_paths_arg_trims_whitespace(
    run_once_env: Path,
    prompt_capture: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    src = run_once_env / "src"
    src.mkdir()
    (src / "foo.py").write_text("print('foo')\n", encoding="utf-8")
    (src / "bar.py").write_text("print('bar')\n", encoding="utf-8")
    continuous_refactoring.run_command(["git", "add", "src"], cwd=run_once_env)
    continuous_refactoring.run_command(
        ["git", "commit", "-m", "add spaced paths"], cwd=run_once_env,
    )

    monkeypatch.setattr(
        "continuous_refactoring.routing_pipeline.classify_target", _classifier_trap,
    )
    args = make_run_once_args(run_once_env, paths="src/foo.py: src/bar.py")
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0
    assert len(prompt_capture) == 1
    assert "- src/foo.py" in prompt_capture[0]
    assert "- src/bar.py" in prompt_capture[0]
    assert "-  src/bar.py" not in prompt_capture[0]


# ---------------------------------------------------------------------------
# Case B: run_once stays on the user's branch and produces a diffstat
# ---------------------------------------------------------------------------


def test_run_once_stays_on_invoked_branch(
    run_once_env: Path,
    prompt_capture: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "continuous_refactoring.routing_pipeline.classify_target", _classifier_trap,
    )
    starting_branch = continuous_refactoring.current_branch(run_once_env)
    args = make_run_once_args(run_once_env)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0
    assert continuous_refactoring.current_branch(run_once_env) == starting_branch
    assert "Branch:" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Case C: run_loop 2-target batch — invocations, commit prefix, local commits
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
        "continuous_refactoring.routing_pipeline.classify_target", _classifier_trap,
    )

    agent_calls: list[str] = []
    def tracking_agent(**kwargs: object) -> CommandCapture:
        agent_calls.append(str(kwargs.get("prompt", "")))
        rr = Path(str(kwargs.get("repo_root", "")))
        (rr / f"change{len(agent_calls)}.txt").write_text("x\n", encoding="utf-8")
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", tracking_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    targets_file = tmp_path / "targets.jsonl"
    lines = [
        json.dumps({"description": "target-0", "files": ["a.py"]}),
        json.dumps({"description": "target-1", "files": ["b.py"]}),
    ]
    targets_file.write_text("\n".join(lines), encoding="utf-8")

    args = make_run_loop_args(
        repo_root,
        targets=targets_file,
        commit_message_prefix="continuous refactor",
    )
    exit_code = continuous_refactoring.run_loop(args)

    assert exit_code == 0
    assert len(agent_calls) == 2

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
        "continuous_refactoring.routing_pipeline.classify_target", stub_classifier,
    )

    args = make_run_once_args(run_once_env)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0
    assert len(classify_calls) == 1

    assert len(prompt_capture) == 1
    expected = _expected_one_shot_prompt(run_once_env, args.validation_command)
    assert prompt_capture[0] == expected

    assert "Branch:" not in capsys.readouterr().out
