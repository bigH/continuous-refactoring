from __future__ import annotations

import json
from pathlib import Path

import pytest

from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.planning_state import (
    CompletedPlanningStep,
    PlanningState,
    append_planning_feedback,
    complete_planning_step,
    load_planning_state,
    new_planning_state,
    planning_stage_stdout_path,
    planning_state_path,
    planning_step_stdout,
    reopen_planning_for_revise,
    save_planning_state,
    write_planning_stage_stdout,
)


_NOW = "2026-04-29T12:00:00.000+00:00"
_LATER = "2026-04-29T12:01:00.000+00:00"


def _migration_root(tmp_path: Path) -> tuple[Path, Path]:
    repo_root = tmp_path
    mig_root = repo_root / "migrations" / "auth-cleanup"
    mig_root.mkdir(parents=True)
    return repo_root, mig_root


def _write_stdout(repo_root: Path, mig_root: Path, step: str, text: str = "ok\n") -> str:
    path = planning_stage_stdout_path(mig_root, step)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path.relative_to(repo_root).as_posix()


def _completed(
    repo_root: Path,
    mig_root: Path,
    name: str,
    outcome: str = "completed",
) -> CompletedPlanningStep:
    return CompletedPlanningStep(
        name=name,
        completed_at=_LATER,
        outcome=outcome,
        outputs={"stdout": _write_stdout(repo_root, mig_root, name)},
    )


def _write_state_payload(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _payload(
    *,
    repo_root: Path,
    mig_root: Path,
    next_step: str,
    completed_steps: list[dict[str, object]] | None = None,
    review_findings: str | None = None,
    final_decision: str | None = None,
    final_reason: str | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "target": "Clean up auth",
        "next_step": next_step,
        "completed_steps": completed_steps or [],
        "started_at": _NOW,
        "updated_at": _LATER,
        "feedback": [],
        "review_findings": review_findings,
        "final_decision": final_decision,
        "final_reason": final_reason,
    }


def test_planning_state_roundtrip_preserves_completed_steps_and_current_step(
    tmp_path: Path,
) -> None:
    repo_root, mig_root = _migration_root(tmp_path)
    state = new_planning_state("Clean up auth", now=_NOW)
    outputs = {"stdout": _write_stdout(repo_root, mig_root, "approaches")}
    updated = complete_planning_step(
        state,
        "approaches",
        "completed",
        outputs,
        completed_at=_LATER,
        agent="codex",
        model="gpt-5.5",
        effort="low",
    )

    save_planning_state(updated, planning_state_path(mig_root), repo_root=repo_root)
    loaded = load_planning_state(repo_root, planning_state_path(mig_root))

    assert loaded.next_step == "pick-best"
    assert [step.name for step in loaded.completed_steps] == ["approaches"]
    assert loaded.completed_steps[0].outputs == outputs
    assert loaded.completed_steps[0].agent == "codex"
    assert loaded.completed_steps[0].model == "gpt-5.5"
    assert loaded.completed_steps[0].effort == "low"


def test_planning_state_defaults_new_plan_to_first_step() -> None:
    state = new_planning_state("Clean up auth", now=_NOW)

    assert state.schema_version == 1
    assert state.target == "Clean up auth"
    assert state.next_step == "approaches"
    assert state.completed_steps == ()
    assert state.review_findings is None
    assert state.final_decision is None
    assert state.final_reason is None


def test_planning_state_records_user_refinement_feedback(tmp_path: Path) -> None:
    repo_root, mig_root = _migration_root(tmp_path)
    state = new_planning_state("Clean up auth", now=_NOW)

    state = append_planning_feedback(
        state,
        "Keep rollout separate.",
        "message",
        now=_NOW,
    )
    state = append_planning_feedback(
        state,
        "Use the staged publisher.",
        "file",
        now=_LATER,
    )
    save_planning_state(state, planning_state_path(mig_root), repo_root=repo_root)

    payload = json.loads(planning_state_path(mig_root).read_text(encoding="utf-8"))
    assert payload["feedback"] == [
        {
            "received_at": _NOW,
            "source": "message",
            "text": "Keep rollout separate.",
        },
        {
            "received_at": _LATER,
            "source": "file",
            "text": "Use the staged publisher.",
        },
    ]

    loaded = load_planning_state(repo_root, planning_state_path(mig_root))
    assert [feedback.source for feedback in loaded.feedback] == ["message", "file"]
    assert [feedback.text for feedback in loaded.feedback] == [
        "Keep rollout separate.",
        "Use the staged publisher.",
    ]


def test_repeated_planning_step_stdout_keeps_prior_audit_output(
    tmp_path: Path,
) -> None:
    repo_root, mig_root = _migration_root(tmp_path)

    first = write_planning_stage_stdout(repo_root, mig_root, "final-review", "first\n")
    second = write_planning_stage_stdout(repo_root, mig_root, "final-review", "second\n")

    assert first == {
        "stdout": "migrations/auth-cleanup/.planning/stages/final-review.stdout.md"
    }
    assert second == {
        "stdout": "migrations/auth-cleanup/.planning/stages/final-review-2.stdout.md"
    }
    assert planning_stage_stdout_path(mig_root, "final-review").read_text(
        encoding="utf-8"
    ) == "first\n"
    assert (
        mig_root / ".planning" / "stages" / "final-review-2.stdout.md"
    ).read_text(encoding="utf-8") == "second\n"


def test_reopen_planning_for_revise_appends_revision_anchors(
    tmp_path: Path,
) -> None:
    repo_root, mig_root = _migration_root(tmp_path)
    state = new_planning_state("Clean up auth", now=_NOW)

    for step, outcome in (
        ("approaches", "completed"),
        ("pick-best", "completed"),
        ("expand", "completed"),
        ("review", "clear"),
        ("final-review", "approve-auto"),
    ):
        state = complete_planning_step(
            state,
            step,
            outcome,
            write_planning_stage_stdout(repo_root, mig_root, step, f"{step}\n"),
            completed_at=_LATER,
            final_reason="ready" if step == "final-review" else None,
        )

    state = reopen_planning_for_revise(state, now=_LATER)
    assert state.next_step == "revise"
    assert state.revision_base_step_counts == (5,)

    for step, outcome in (
        ("revise", "completed"),
        ("review-2", "clear"),
        ("final-review", "approve-auto"),
    ):
        state = complete_planning_step(
            state,
            step,
            outcome,
            write_planning_stage_stdout(repo_root, mig_root, step, f"{step} again\n"),
            completed_at=_LATER,
            final_reason="ready again" if step == "final-review" else None,
        )

    state = reopen_planning_for_revise(state, now=_LATER)
    save_planning_state(state, planning_state_path(mig_root), repo_root=repo_root)
    loaded = load_planning_state(repo_root, planning_state_path(mig_root))

    assert loaded.next_step == "revise"
    assert loaded.revision_base_step_counts == (5, 8)


def test_legacy_revision_base_step_count_decodes_as_single_anchor(
    tmp_path: Path,
) -> None:
    repo_root, mig_root = _migration_root(tmp_path)
    state = new_planning_state("Clean up auth", now=_NOW)

    for step, outcome in (
        ("approaches", "completed"),
        ("pick-best", "completed"),
        ("expand", "completed"),
        ("review", "clear"),
        ("final-review", "approve-auto"),
    ):
        state = complete_planning_step(
            state,
            step,
            outcome,
            write_planning_stage_stdout(repo_root, mig_root, step, f"{step}\n"),
            completed_at=_LATER,
            final_reason="ready" if step == "final-review" else None,
        )

    payload = _payload(
        repo_root=repo_root,
        mig_root=mig_root,
        next_step="revise",
        completed_steps=[step.to_payload() for step in state.completed_steps],
    )
    payload["revision_base_step_count"] = 5
    _write_state_payload(planning_state_path(mig_root), payload)

    loaded = load_planning_state(repo_root, planning_state_path(mig_root))
    assert loaded.next_step == "revise"
    assert loaded.revision_base_step_counts == (5,)
    assert loaded.revision_base_step_count == 5

    save_planning_state(loaded, planning_state_path(mig_root), repo_root=repo_root)
    saved = json.loads(planning_state_path(mig_root).read_text(encoding="utf-8"))
    assert saved["revision_base_step_counts"] == [5]
    assert "revision_base_step_count" not in saved


def test_planning_state_rejects_unknown_current_step(tmp_path: Path) -> None:
    repo_root, mig_root = _migration_root(tmp_path)
    path = planning_state_path(mig_root)
    _write_state_payload(
        path,
        _payload(repo_root=repo_root, mig_root=mig_root, next_step="wat"),
    )

    with pytest.raises(ContinuousRefactorError, match="Unknown planning cursor"):
        load_planning_state(repo_root, path)


def test_planning_state_rejects_completed_step_after_current_step(
    tmp_path: Path,
) -> None:
    repo_root, mig_root = _migration_root(tmp_path)
    path = planning_state_path(mig_root)
    _write_state_payload(
        path,
        _payload(
            repo_root=repo_root,
            mig_root=mig_root,
            next_step="pick-best",
            completed_steps=[
                {
                    "name": "approaches",
                    "completed_at": _LATER,
                    "outcome": "completed",
                    "outputs": {
                        "stdout": _write_stdout(repo_root, mig_root, "approaches")
                    },
                },
                {
                    "name": "pick-best",
                    "completed_at": _LATER,
                    "outcome": "completed",
                    "outputs": {
                        "stdout": _write_stdout(repo_root, mig_root, "pick-best")
                    },
                },
            ],
        ),
    )

    with pytest.raises(ContinuousRefactorError, match="does not match replayed cursor"):
        load_planning_state(repo_root, path)


def test_planning_state_rejects_review_to_final_review_when_findings_required_revise(
    tmp_path: Path,
) -> None:
    repo_root, mig_root = _migration_root(tmp_path)
    review_path = _write_stdout(repo_root, mig_root, "review", "1. Fix it.\n")
    path = planning_state_path(mig_root)
    _write_state_payload(
        path,
        _payload(
            repo_root=repo_root,
            mig_root=mig_root,
            next_step="final-review",
            review_findings=review_path,
            completed_steps=[
                _completed(repo_root, mig_root, "approaches").to_payload(),
                _completed(repo_root, mig_root, "pick-best").to_payload(),
                _completed(repo_root, mig_root, "expand").to_payload(),
                {
                    "name": "review",
                    "completed_at": _LATER,
                    "outcome": "findings",
                    "outputs": {"stdout": review_path},
                },
            ],
        ),
    )

    with pytest.raises(ContinuousRefactorError, match="does not match replayed cursor"):
        load_planning_state(repo_root, path)


def test_planning_state_rejects_revise_without_prior_review_findings(
    tmp_path: Path,
) -> None:
    repo_root, mig_root = _migration_root(tmp_path)
    path = planning_state_path(mig_root)
    _write_state_payload(
        path,
        _payload(
            repo_root=repo_root,
            mig_root=mig_root,
            next_step="review-2",
            completed_steps=[
                _completed(repo_root, mig_root, "approaches").to_payload(),
                _completed(repo_root, mig_root, "pick-best").to_payload(),
                _completed(repo_root, mig_root, "expand").to_payload(),
                _completed(repo_root, mig_root, "review", "clear").to_payload(),
                _completed(repo_root, mig_root, "revise").to_payload(),
            ],
        ),
    )

    with pytest.raises(ContinuousRefactorError, match="expected final-review"):
        load_planning_state(repo_root, path)


def test_planning_state_replays_branching_transition_history(tmp_path: Path) -> None:
    repo_root, mig_root = _migration_root(tmp_path)
    state = new_planning_state("Clean up auth", now=_NOW)
    for name in ("approaches", "pick-best", "expand"):
        state = complete_planning_step(
            state,
            name,
            "completed",
            {"stdout": _write_stdout(repo_root, mig_root, name)},
            completed_at=_LATER,
        )
    review_path = _write_stdout(repo_root, mig_root, "review", "1. Fix it.\n")
    state = complete_planning_step(
        state,
        "review",
        "findings",
        {"stdout": review_path},
        completed_at=_LATER,
    )
    state = complete_planning_step(
        state,
        "revise",
        "completed",
        {"stdout": _write_stdout(repo_root, mig_root, "revise")},
        completed_at=_LATER,
    )
    state = complete_planning_step(
        state,
        "review-2",
        "clear",
        {"stdout": _write_stdout(repo_root, mig_root, "review-2")},
        completed_at=_LATER,
    )

    save_planning_state(state, planning_state_path(mig_root), repo_root=repo_root)
    loaded = load_planning_state(repo_root, planning_state_path(mig_root))

    assert loaded.next_step == "final-review"
    assert loaded.review_findings == review_path
    assert [step.name for step in loaded.completed_steps] == [
        "approaches",
        "pick-best",
        "expand",
        "review",
        "revise",
        "review-2",
    ]


def test_planning_state_rejects_missing_artifact_for_completed_step(
    tmp_path: Path,
) -> None:
    repo_root, mig_root = _migration_root(tmp_path)
    state = PlanningState(
        schema_version=1,
        target="Clean up auth",
        next_step="pick-best",
        completed_steps=(
            CompletedPlanningStep(
                name="approaches",
                completed_at=_LATER,
                outcome="completed",
                outputs={
                    "stdout": (
                        mig_root / ".planning" / "stages" / "approaches.stdout.md"
                    ).relative_to(repo_root).as_posix()
                },
            ),
        ),
        started_at=_NOW,
        updated_at=_LATER,
        feedback=(),
        review_findings=None,
        final_decision=None,
        final_reason=None,
    )
    _write_state_payload(
        planning_state_path(mig_root),
        {
            "schema_version": state.schema_version,
            "target": state.target,
            "next_step": state.next_step,
            "completed_steps": [
                step.to_payload() for step in state.completed_steps
            ],
            "started_at": state.started_at,
            "updated_at": state.updated_at,
            "feedback": list(state.feedback),
            "review_findings": state.review_findings,
            "final_decision": state.final_decision,
            "final_reason": state.final_reason,
        },
    )

    with pytest.raises(ContinuousRefactorError, match="missing planning output"):
        load_planning_state(repo_root, planning_state_path(mig_root))


@pytest.mark.parametrize(
    ("stdout_ref", "message"),
    [
        ("/tmp/agent.stdout.log", "repo-relative"),
        ("../escape.stdout.md", "repo-relative"),
        ("outside/stdout.md", "inside the migration directory"),
        (
            "migrations/auth-cleanup/.planning/stages/missing.stdout.md",
            "missing planning output",
        ),
    ],
)
def test_save_planning_state_rejects_invalid_output_refs_before_replacing(
    tmp_path: Path,
    stdout_ref: str,
    message: str,
) -> None:
    repo_root, mig_root = _migration_root(tmp_path)
    path = planning_state_path(mig_root)
    path.parent.mkdir(parents=True)
    original_content = '{"schema_version": 0}\n'
    path.write_text(original_content, encoding="utf-8")
    outside = repo_root / "outside" / "stdout.md"
    outside.parent.mkdir()
    outside.write_text("outside\n", encoding="utf-8")
    state = PlanningState(
        schema_version=1,
        target="Clean up auth",
        next_step="pick-best",
        completed_steps=(
            CompletedPlanningStep(
                name="approaches",
                completed_at=_LATER,
                outcome="completed",
                outputs={"stdout": stdout_ref},
            ),
        ),
        started_at=_NOW,
        updated_at=_LATER,
        feedback=(),
        review_findings=None,
        final_decision=None,
        final_reason=None,
    )

    with pytest.raises(ContinuousRefactorError, match=message):
        save_planning_state(state, path, repo_root=repo_root)

    assert path.read_text(encoding="utf-8") == original_content


def test_planning_state_atomic_save_preserves_existing_file_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, mig_root = _migration_root(tmp_path)
    path = planning_state_path(mig_root)
    path.parent.mkdir(parents=True)
    original_content = '{"schema_version": 0}\n'
    path.write_text(original_content, encoding="utf-8")

    def fail_replace(self: Path, target: Path) -> Path:
        raise OSError(f"cannot replace {target} from {self}")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(ContinuousRefactorError, match=f"Could not save planning state {path}"):
        save_planning_state(
            new_planning_state("Clean up auth", now=_NOW),
            path,
            repo_root=tmp_path,
        )

    assert path.read_text(encoding="utf-8") == original_content
    assert list(path.parent.glob("*.tmp")) == []


def test_complete_planning_step_rejects_impossible_in_memory_cursor(
    tmp_path: Path,
) -> None:
    repo_root, mig_root = _migration_root(tmp_path)
    state = PlanningState(
        schema_version=1,
        target="Clean up auth",
        next_step="pick-best",
        completed_steps=(),
        started_at=_NOW,
        updated_at=_NOW,
        feedback=(),
        review_findings=None,
        final_decision=None,
        final_reason=None,
    )

    with pytest.raises(ContinuousRefactorError, match="does not match replayed cursor"):
        complete_planning_step(
            state,
            "pick-best",
            "completed",
            {"stdout": _write_stdout(repo_root, mig_root, "pick-best")},
            completed_at=_LATER,
        )


def test_complete_planning_step_rejects_absolute_output_ref(tmp_path: Path) -> None:
    state = new_planning_state("Clean up auth", now=_NOW)

    with pytest.raises(ContinuousRefactorError, match="repo-relative"):
        complete_planning_step(
            state,
            "approaches",
            "completed",
            {"stdout": str(tmp_path / "agent.stdout.log")},
            completed_at=_LATER,
        )


def test_planning_step_stdout_rejects_unvalidated_output_ref(tmp_path: Path) -> None:
    repo_root, mig_root = _migration_root(tmp_path)
    state = PlanningState(
        schema_version=1,
        target="Clean up auth",
        next_step="pick-best",
        completed_steps=(
            CompletedPlanningStep(
                name="approaches",
                completed_at=_LATER,
                outcome="completed",
                outputs={"stdout": str(tmp_path / "agent.stdout.log")},
            ),
        ),
        started_at=_NOW,
        updated_at=_LATER,
        feedback=(),
        review_findings=None,
        final_decision=None,
        final_reason=None,
    )

    with pytest.raises(ContinuousRefactorError, match="repo-relative"):
        planning_step_stdout(
            state,
            repo_root,
            "approaches",
            state_path=planning_state_path(mig_root),
        )


def test_planning_state_snapshot_paths_are_repo_relative(tmp_path: Path) -> None:
    repo_root, mig_root = _migration_root(tmp_path)
    path = planning_state_path(mig_root)
    absolute_payload = _payload(
        repo_root=repo_root,
        mig_root=mig_root,
        next_step="pick-best",
        completed_steps=[
            {
                "name": "approaches",
                "completed_at": _LATER,
                "outcome": "completed",
                "outputs": {"stdout": str(tmp_path / "tmp" / "agent.stdout.log")},
            }
        ],
    )
    _write_state_payload(path, absolute_payload)

    with pytest.raises(ContinuousRefactorError, match="repo-relative"):
        load_planning_state(repo_root, path)

    escape_payload = dict(absolute_payload)
    escape_payload["completed_steps"] = [
        {
            "name": "approaches",
            "completed_at": _LATER,
            "outcome": "completed",
            "outputs": {"stdout": "../escape.stdout.md"},
        }
    ]
    _write_state_payload(path, escape_payload)

    with pytest.raises(ContinuousRefactorError, match="repo-relative"):
        load_planning_state(repo_root, path)

    valid_ref = _write_stdout(repo_root, mig_root, "approaches")
    _write_state_payload(
        path,
        _payload(
            repo_root=repo_root,
            mig_root=mig_root,
            next_step="pick-best",
            completed_steps=[
                {
                    "name": "approaches",
                    "completed_at": _LATER,
                    "outcome": "completed",
                    "outputs": {"stdout": valid_ref},
                }
            ],
        ),
    )

    assert load_planning_state(repo_root, path).completed_steps[0].outputs["stdout"] == valid_ref
