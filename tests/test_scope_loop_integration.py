from __future__ import annotations

from pathlib import Path

import pytest

import continuous_refactoring
import continuous_refactoring.loop
import continuous_refactoring.routing_pipeline
from continuous_refactoring.artifacts import (
    ContinuousRefactorError,
    RunArtifacts,
    create_run_artifacts,
)
from continuous_refactoring.decisions import DecisionRecord
from continuous_refactoring.routing_pipeline import RouteResult
from continuous_refactoring.targeting import Target

from conftest import init_repo, make_run_once_args


EXPANDED_FILES = ("README.md", "src/expanded.py")
LIVE_MIGRATIONS_DIR = ".migrations"


@pytest.fixture
def routing_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, RunArtifacts]:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    _patch_live_migrations_dir(monkeypatch, repo_root)
    tmpdir = tmp_path / "tmpdir"
    tmpdir.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmpdir))
    artifacts = create_run_artifacts(
        repo_root=repo_root,
        agent="codex",
        model="fake",
        effort="low",
        test_command="true",
    )
    monkeypatch.setattr(
        "continuous_refactoring.migration_tick.try_migration_tick",
        lambda *_args, **_kwargs: ("not-routed", None),
    )
    return repo_root, artifacts


def _patch_live_migrations_dir(
    monkeypatch: pytest.MonkeyPatch, repo_root: Path,
) -> Path:
    live_dir = repo_root / LIVE_MIGRATIONS_DIR
    live_dir.mkdir()
    monkeypatch.setattr(
        "continuous_refactoring.loop._resolve_live_migrations_dir",
        lambda _repo_root: live_dir,
    )
    return live_dir


def _patch_scope_expansion(
    monkeypatch: pytest.MonkeyPatch,
    *,
    files: tuple[str, ...] = EXPANDED_FILES,
    context: str,
) -> None:
    monkeypatch.setattr(
        "continuous_refactoring.routing_pipeline.expand_target_for_classification",
        lambda target, *_args, **_kwargs: (
            Target(
                description=target.description,
                files=files,
                provenance=target.provenance,
            ),
            context,
        ),
    )


def _invoke_route_and_run(
    repo_root: Path, artifacts: RunArtifacts, target: Target,
) -> RouteResult:
    return continuous_refactoring.routing_pipeline.route_and_run(
        target,
        "taste",
        repo_root,
        artifacts,
        live_dir=repo_root / LIVE_MIGRATIONS_DIR,
        agent="codex",
        model="fake",
        effort="low",
        timeout=None,
        commit_message_prefix="continuous refactor",
        validation_command="uv run pytest",
        max_attempts=1,
        attempt=1,
        finalize_commit=continuous_refactoring.loop._finalize_commit,
    )


def _single_prompt(prompt_capture: list[str]) -> str:
    assert len(prompt_capture) == 1
    return prompt_capture[0]


def test_expanded_target_reaches_classifier(
    routing_env: tuple[Path, RunArtifacts],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root, artifacts = routing_env
    seen_files: list[tuple[str, ...]] = []

    _patch_scope_expansion(
        monkeypatch,
        context="Selected scope candidate: cross-cluster",
    )

    def fake_classifier(target: Target, *_args: object, **_kwargs: object) -> str:
        seen_files.append(target.files)
        return "cohesive-cleanup"

    monkeypatch.setattr(
        "continuous_refactoring.routing_pipeline.classify_target",
        fake_classifier,
    )

    result = _invoke_route_and_run(
        repo_root,
        artifacts,
        Target(description="seed", files=("README.md",), provenance="globs"),
    )

    assert seen_files == [EXPANDED_FILES]
    assert result.target.files == EXPANDED_FILES


def test_deferred_migration_tick_falls_through_to_classifier(
    routing_env: tuple[Path, RunArtifacts],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root, artifacts = routing_env
    classifier_calls: list[str] = []
    record = DecisionRecord(
        decision="retry",
        retry_recommendation="same-target",
        target="migration/deferred",
        call_role="phase.ready-check",
        phase_reached="phase.ready-check",
        failure_kind="phase-ready-no",
        summary="not ready yet",
    )

    monkeypatch.setattr(
        "continuous_refactoring.migration_tick.try_migration_tick",
        lambda *_args, **_kwargs: ("not-routed", record),
    )

    def fake_classifier(target: Target, *_args: object, **_kwargs: object) -> str:
        classifier_calls.append(target.description)
        return "cohesive-cleanup"

    monkeypatch.setattr(
        "continuous_refactoring.routing_pipeline.classify_target",
        fake_classifier,
    )

    result = _invoke_route_and_run(
        repo_root,
        artifacts,
        Target(description="seed", files=("README.md",), provenance="globs"),
    )

    assert result.outcome == "not-routed"
    assert classifier_calls == ["seed"]


def test_cohesive_cleanup_runs_one_shot_against_expanded_files(
    run_once_env: Path,
    prompt_capture: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_live_migrations_dir(monkeypatch, run_once_env)
    (run_once_env / "src").mkdir()
    (run_once_env / "src" / "expanded.py").write_text("VALUE = 1\n", encoding="utf-8")
    continuous_refactoring.run_command(["git", "add", "src/expanded.py"], cwd=run_once_env)
    continuous_refactoring.run_command(
        ["git", "commit", "-m", "add expanded"], cwd=run_once_env,
    )

    _patch_scope_expansion(
        monkeypatch,
        context="Selected scope candidate: local-cluster",
    )
    monkeypatch.setattr(
        "continuous_refactoring.routing_pipeline.classify_target",
        lambda *_args, **_kwargs: "cohesive-cleanup",
    )

    exit_code = continuous_refactoring.run_once(make_run_once_args(run_once_env))
    prompt = _single_prompt(prompt_capture)

    assert exit_code == 0
    assert "- README.md" in prompt
    assert "- src/expanded.py" in prompt


def test_needs_plan_receives_expanded_scope_context(
    routing_env: tuple[Path, RunArtifacts],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root, artifacts = routing_env
    captured: dict[str, str] = {}
    planning_context = "Selected scope candidate: cross-cluster\n- src/foo.py\n- tests/test_foo.py"

    _patch_scope_expansion(
        monkeypatch,
        files=("src/foo.py", "tests/test_foo.py"),
        context=planning_context,
    )
    monkeypatch.setattr(
        "continuous_refactoring.routing_pipeline.classify_target",
        lambda *_args, **_kwargs: "needs-plan",
    )

    class StubPlanningStepResult:
        status = "published"
        step = "approaches"
        next_step = "pick-best"
        terminal_outcome = None
        reason = "stub"

    def fake_run_next_planning_step(*_args: object, **kwargs: object) -> StubPlanningStepResult:
        captured["extra_context"] = str(kwargs["extra_context"])
        return StubPlanningStepResult()

    monkeypatch.setattr(
        "continuous_refactoring.routing_pipeline.run_next_planning_step",
        fake_run_next_planning_step,
    )

    result = _invoke_route_and_run(
        repo_root,
        artifacts,
        Target(description="seed", files=("src/foo.py",), provenance="globs"),
    )

    assert result.outcome == "commit"
    assert captured["extra_context"] == planning_context


def test_classifier_failure_returns_abandon_record(
    routing_env: tuple[Path, RunArtifacts],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root, artifacts = routing_env
    target = Target(description="seed", files=("README.md",), provenance="globs")

    monkeypatch.setattr(
        "continuous_refactoring.routing_pipeline.classify_target",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ContinuousRefactorError("transport failed")
        ),
    )

    result = _invoke_route_and_run(repo_root, artifacts, target)

    assert result.outcome == "abandon"
    assert result.decision_record == DecisionRecord(
        decision="abandon",
        retry_recommendation="new-target",
        target="seed",
        call_role="classify",
        phase_reached="classify",
        failure_kind="agent-infra-failure",
        summary="transport failed",
    )


def test_planning_failure_uses_stage_label_in_abandon_record(
    routing_env: tuple[Path, RunArtifacts],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root, artifacts = routing_env

    _patch_scope_expansion(
        monkeypatch,
        files=("src/foo.py",),
        context="Selected scope candidate: local-cluster",
    )
    monkeypatch.setattr(
        "continuous_refactoring.routing_pipeline.classify_target",
        lambda *_args, **_kwargs: "needs-plan",
    )
    monkeypatch.setattr(
        "continuous_refactoring.routing_pipeline.run_next_planning_step",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ContinuousRefactorError(
                "planning.review-2 failed: revised plan still has findings"
            )
        ),
    )

    result = _invoke_route_and_run(
        repo_root,
        artifacts,
        Target(description="seed", files=("src/foo.py",), provenance="globs"),
    )

    assert result.outcome == "abandon"
    assert result.decision_record == DecisionRecord(
        decision="abandon",
        retry_recommendation="new-target",
        target="seed",
        call_role="planning.review-2",
        phase_reached="planning.review-2",
        failure_kind="agent-infra-failure",
        summary="planning.review-2 failed: revised plan still has findings",
    )


def test_live_migrations_unset_skips_scope_expansion_and_classification(
    run_once_env: Path,
    prompt_capture: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def trap(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("routing helpers must not run without live_migrations_dir")

    monkeypatch.setattr("continuous_refactoring.routing_pipeline.classify_target", trap)
    monkeypatch.setattr("continuous_refactoring.routing_pipeline.expand_target_for_classification", trap)

    exit_code = continuous_refactoring.run_once(make_run_once_args(run_once_env))

    assert exit_code == 0
    _single_prompt(prompt_capture)
