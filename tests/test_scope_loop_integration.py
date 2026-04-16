from __future__ import annotations

from pathlib import Path

import pytest

import continuous_refactoring
import continuous_refactoring.loop
from continuous_refactoring.artifacts import RunArtifacts, create_run_artifacts
from continuous_refactoring.targeting import Target

from conftest import init_repo, make_run_once_args


def _make_artifacts(
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> RunArtifacts:
    tmpdir = tmp_path / "tmpdir"
    tmpdir.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmpdir))
    return create_run_artifacts(
        repo_root=repo_root,
        agent="codex",
        model="fake",
        effort="low",
        test_command="true",
    )


def test_expanded_target_reaches_classifier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    live_dir = repo_root / ".migrations"
    live_dir.mkdir()
    artifacts = _make_artifacts(repo_root, tmp_path, monkeypatch)

    seen_files: list[tuple[str, ...]] = []

    monkeypatch.setattr(
        "continuous_refactoring.loop._resolve_live_migrations_dir",
        lambda _repo_root: live_dir,
    )
    monkeypatch.setattr(
        "continuous_refactoring.loop._try_migration_tick",
        lambda *_args, **_kwargs: "not-routed",
    )
    monkeypatch.setattr(
        "continuous_refactoring.loop._expand_target_for_classification",
        lambda target, *_args, **_kwargs: (
            Target(
                description=target.description,
                files=("README.md", "src/expanded.py"),
                provenance=target.provenance,
            ),
            "Selected scope candidate: cross-cluster",
        ),
    )

    def fake_classifier(target: Target, *_args: object, **_kwargs: object) -> str:
        seen_files.append(target.files)
        return "cohesive-cleanup"

    monkeypatch.setattr("continuous_refactoring.loop.classify_target", fake_classifier)

    result = continuous_refactoring.loop._route_and_run(
        Target(description="seed", files=("README.md",), provenance="globs"),
        "taste",
        repo_root,
        artifacts,
        agent="codex",
        model="fake",
        effort="low",
        timeout=None,
        commit_message_prefix="continuous refactor",
        attempt=1,
    )

    assert seen_files == [("README.md", "src/expanded.py")]
    assert result.target.files == ("README.md", "src/expanded.py")


def test_cohesive_cleanup_runs_one_shot_against_expanded_files(
    run_once_env: Path,
    prompt_capture: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = run_once_env / ".migrations"
    live_dir.mkdir()
    (run_once_env / "src").mkdir()
    (run_once_env / "src" / "expanded.py").write_text("VALUE = 1\n", encoding="utf-8")
    continuous_refactoring.run_command(["git", "add", "src/expanded.py"], cwd=run_once_env)
    continuous_refactoring.run_command(
        ["git", "commit", "-m", "add expanded"], cwd=run_once_env,
    )

    monkeypatch.setattr(
        "continuous_refactoring.loop._resolve_live_migrations_dir",
        lambda _repo_root: live_dir,
    )
    monkeypatch.setattr(
        "continuous_refactoring.loop._expand_target_for_classification",
        lambda target, *_args, **_kwargs: (
            Target(
                description=target.description,
                files=("README.md", "src/expanded.py"),
                provenance=target.provenance,
            ),
            "Selected scope candidate: local-cluster",
        ),
    )
    monkeypatch.setattr(
        "continuous_refactoring.loop.classify_target",
        lambda *_args, **_kwargs: "cohesive-cleanup",
    )

    exit_code = continuous_refactoring.run_once(make_run_once_args(run_once_env))

    assert exit_code == 0
    assert len(prompt_capture) == 1
    assert "- README.md" in prompt_capture[0]
    assert "- src/expanded.py" in prompt_capture[0]


def test_needs_plan_receives_expanded_scope_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    live_dir = repo_root / ".migrations"
    live_dir.mkdir()
    artifacts = _make_artifacts(repo_root, tmp_path, monkeypatch)

    captured: dict[str, str] = {}
    planning_context = "Selected scope candidate: cross-cluster\n- src/foo.py\n- tests/test_foo.py"

    monkeypatch.setattr(
        "continuous_refactoring.loop._resolve_live_migrations_dir",
        lambda _repo_root: live_dir,
    )
    monkeypatch.setattr(
        "continuous_refactoring.loop._try_migration_tick",
        lambda *_args, **_kwargs: "not-routed",
    )
    monkeypatch.setattr(
        "continuous_refactoring.loop._expand_target_for_classification",
        lambda target, *_args, **_kwargs: (
            Target(
                description=target.description,
                files=("src/foo.py", "tests/test_foo.py"),
                provenance=target.provenance,
            ),
            planning_context,
        ),
    )
    monkeypatch.setattr(
        "continuous_refactoring.loop.classify_target",
        lambda *_args, **_kwargs: "needs-plan",
    )

    class StubPlanningOutcome:
        status = "ready"
        reason = "stub"

    def fake_run_planning(*_args: object, **kwargs: object) -> StubPlanningOutcome:
        captured["extra_context"] = str(kwargs["extra_context"])
        return StubPlanningOutcome()

    monkeypatch.setattr("continuous_refactoring.loop.run_planning", fake_run_planning)

    result = continuous_refactoring.loop._route_and_run(
        Target(description="seed", files=("src/foo.py",), provenance="globs"),
        "taste",
        repo_root,
        artifacts,
        agent="codex",
        model="fake",
        effort="low",
        timeout=None,
        commit_message_prefix="continuous refactor",
        attempt=1,
    )

    assert result.outcome == "success"
    assert captured["extra_context"] == planning_context


def test_live_migrations_unset_skips_scope_expansion_and_classification(
    run_once_env: Path,
    prompt_capture: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def trap(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("routing helpers must not run without live_migrations_dir")

    monkeypatch.setattr("continuous_refactoring.loop.classify_target", trap)
    monkeypatch.setattr("continuous_refactoring.loop._expand_target_for_classification", trap)

    exit_code = continuous_refactoring.run_once(make_run_once_args(run_once_env))

    assert exit_code == 0
    assert len(prompt_capture) == 1
