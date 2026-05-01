from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import init_repo
from continuous_refactoring.artifacts import (
    CommandCapture,
    ContinuousRefactorError,
    RunArtifacts,
    create_run_artifacts,
)
from continuous_refactoring.migrations import (
    MigrationManifest,
    load_manifest,
    migration_root,
    save_manifest,
)
from continuous_refactoring.planning import (
    _build_durable_planning_context,
    _parse_final_decision,
    _refresh_manifest,
    _review_has_findings,
    _discover_phase_files,
    PlanningOutcome,
    PlanningRefineRequest,
    run_next_planning_step,
    run_refine_planning_step,
)
from continuous_refactoring.git import run_command
from continuous_refactoring.planning_state import (
    complete_planning_step,
    load_planning_state,
    new_planning_state,
    planning_stage_stdout_path,
    planning_state_path,
    save_planning_state,
)
from continuous_refactoring.planning_publish import snapshot_tree_digest


_TASTE = "- Prefer deletion over wrapping.\n- Fail fast at boundaries."
_TARGET = "Rework auth module for clarity"
_MIGRATION = "rework-auth"


def _planning_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmpdir"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    (tmp_path / "tmpdir").mkdir()
    (tmp_path / "xdg").mkdir()
    init_repo(tmp_path)

    live_dir = tmp_path / "live"
    live_dir.mkdir()
    mig_root = migration_root(live_dir, _MIGRATION)
    return live_dir, mig_root


def _planning_repo_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path]:
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmpdir"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    (tmp_path / "tmpdir").mkdir()
    (tmp_path / "xdg").mkdir()
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    live_dir = repo_root / "live"
    live_dir.mkdir()
    return repo_root, live_dir, migration_root(live_dir, _MIGRATION)


def _commit_all(repo_root: Path, message: str) -> None:
    run_command(["git", "add", "-A"], cwd=repo_root)
    run_command(["git", "commit", "-m", message], cwd=repo_root)


def _planning_decision_response(decision: str, reason: str) -> tuple[str, dict[str, str]]:
    return f"final-decision: {decision} — {reason}\n", {}


def _run_planning(
    tmp_path: Path,
    live_dir: Path,
    responses: list[tuple[str, dict[str, str]]],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[PlanningOutcome, _MockAgent, Path]:
    mig_root = migration_root(live_dir, _MIGRATION)
    mock = _MockAgent(mig_root, responses)
    monkeypatch.setattr("continuous_refactoring.planning.maybe_run_agent", mock)

    outcome: PlanningOutcome | None = None
    while outcome is None:
        result = run_next_planning_step(
            _MIGRATION, _TARGET, _TASTE, tmp_path, live_dir,
            _make_artifacts(tmp_path),
            agent="codex", model="fake", effort="low", timeout=None,
        )
        assert result.status == "published", result.reason
        _commit_all(tmp_path, f"planning {result.step}")
        outcome = result.terminal_outcome
    return outcome, mock, mig_root


def _make_artifacts(tmp_path: Path) -> RunArtifacts:
    return create_run_artifacts(
        repo_root=tmp_path,
        agent="codex",
        model="fake",
        effort="low",
        test_command="true",
    )


class _MockAgent:
    """Sequences mock agent responses, writing files the real agent would."""

    def __init__(
        self,
        mig_root: Path,
        responses: list[tuple[str, dict[str, str]]],
    ) -> None:
        self._mig_root = mig_root
        self._responses = responses
        self._index = 0
        self.call_count = 0
        self.stage_labels: list[str] = []
        self.prompts: list[str] = []

    def __call__(self, **kwargs: object) -> CommandCapture:
        assert self._index < len(self._responses), (
            f"Unexpected agent call #{self._index + 1}"
        )
        stdout, writes = self._responses[self._index]
        self._index += 1
        self.call_count += 1
        self.prompts.append(str(kwargs["prompt"]))
        stdout_path = Path(str(kwargs["stdout_path"]))
        self.stage_labels.append(stdout_path.parent.name)

        migration_dir = _prompt_migration_dir(
            self.prompts[-1],
            Path(str(kwargs["repo_root"])),
        )
        for rel_path, content in writes.items():
            full = migration_dir / rel_path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")

        stderr_path = Path(str(kwargs["stderr_path"]))
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.write_text("", encoding="utf-8")

        return CommandCapture(
            command=("fake",),
            returncode=0,
            stdout=stdout,
            stderr="",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )


class _WorkspaceAgent:
    def __init__(
        self,
        responses: list[tuple[str, dict[str, str], int]],
    ) -> None:
        self._responses = responses
        self._index = 0
        self.stage_labels: list[str] = []
        self.prompts: list[str] = []
        self.migration_dirs: list[Path] = []

    def __call__(self, **kwargs: object) -> CommandCapture:
        assert self._index < len(self._responses), (
            f"Unexpected agent call #{self._index + 1}"
        )
        stdout, writes, returncode = self._responses[self._index]
        self._index += 1
        prompt = str(kwargs["prompt"])
        stdout_path = Path(str(kwargs["stdout_path"]))
        stderr_path = Path(str(kwargs["stderr_path"]))
        migration_dir = _prompt_migration_dir(prompt, Path(str(kwargs["repo_root"])))

        self.prompts.append(prompt)
        self.stage_labels.append(stdout_path.parent.name)
        self.migration_dirs.append(migration_dir)

        for rel_path, content in writes.items():
            full = migration_dir / rel_path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")

        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.write_text("", encoding="utf-8")
        return CommandCapture(
            command=("fake",),
            returncode=returncode,
            stdout=stdout,
            stderr="",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )


def _prompt_migration_dir(prompt: str, repo_root: Path) -> Path:
    for line in prompt.splitlines():
        if line.startswith("Migration directory:"):
            path = Path(line.split(":", 1)[1].strip())
            return path if path.is_absolute() else repo_root / path
    raise AssertionError("Migration directory missing from prompt")


def _workspace_response(
    stdout: str,
    writes: dict[str, str] | None = None,
    *,
    returncode: int = 0,
) -> tuple[str, dict[str, str], int]:
    return stdout, writes or {}, returncode


def _run_next_step(
    repo_root: Path,
    live_dir: Path,
    responses: list[tuple[str, dict[str, str], int]],
    monkeypatch: pytest.MonkeyPatch,
):
    mock = _WorkspaceAgent(responses)
    monkeypatch.setattr("continuous_refactoring.planning.maybe_run_agent", mock)
    result = run_next_planning_step(
        _MIGRATION,
        _TARGET,
        _TASTE,
        repo_root,
        live_dir,
        _make_artifacts(repo_root),
        agent="codex",
        model="fake",
        effort="low",
        timeout=None,
    )
    return result, mock


def _run_refine_step(
    repo_root: Path,
    live_dir: Path,
    responses: list[tuple[str, dict[str, str], int]],
    monkeypatch: pytest.MonkeyPatch,
    *,
    feedback: str = "Refine this plan.",
):
    mock = _WorkspaceAgent(responses)
    monkeypatch.setattr("continuous_refactoring.planning.maybe_run_agent", mock)
    result = run_refine_planning_step(
        PlanningRefineRequest(
            migration_name=_MIGRATION,
            feedback_text=feedback,
            feedback_source="message",
            taste=_TASTE,
            repo_root=repo_root,
            live_dir=live_dir,
            artifacts=_make_artifacts(repo_root),
            agent="codex",
            model="fake",
            effort="low",
        )
    )
    return result, mock


def _seed_planning_snapshot(
    repo_root: Path,
    live_dir: Path,
    completed: list[tuple[str, str, str]],
    *,
    plan_text: str | None = None,
    phase_text: str | None = None,
) -> None:
    mig_root = migration_root(live_dir, _MIGRATION)
    mig_root.mkdir(parents=True, exist_ok=True)
    manifest_path = mig_root / "manifest.json"
    now = "2026-04-29T12:00:00.000+00:00"
    manifest = MigrationManifest(
        name=_MIGRATION,
        created_at=now,
        last_touch=now,
        wake_up_on=None,
        awaiting_human_review=False,
        status="planning",
        current_phase="",
        phases=(),
    )
    save_manifest(manifest, manifest_path)
    if plan_text is not None:
        (mig_root / "plan.md").write_text(plan_text, encoding="utf-8")
    if phase_text is not None:
        (mig_root / "phase-0-setup.md").write_text(phase_text, encoding="utf-8")
        _refresh_manifest(manifest, manifest_path, mig_root=mig_root)

    state = new_planning_state(_TARGET, now=now)
    for step, outcome, stdout in completed:
        stdout_path = planning_stage_stdout_path(mig_root, step)
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text(stdout, encoding="utf-8")
        state = complete_planning_step(
            state,
            step,
            outcome,
            {"stdout": stdout_path.relative_to(repo_root).as_posix()},
            completed_at=now,
        )
    save_planning_state(state, planning_state_path(mig_root), repo_root=repo_root)
    _commit_all(repo_root, "seed planning snapshot")


def _seed_ready_snapshot(repo_root: Path, live_dir: Path) -> None:
    mig_root = migration_root(live_dir, _MIGRATION)
    now = "2026-04-29T12:00:00.000+00:00"
    _seed_planning_snapshot(
        repo_root,
        live_dir,
        [
            ("approaches", "completed", "Generated approaches.\n"),
            ("pick-best", "completed", "Chose incremental.\n"),
            ("expand", "completed", "Expanded.\n"),
            ("review", "clear", "No findings.\n"),
        ],
        plan_text="# Plan\n",
        phase_text=_phase_doc("always", "Setup is complete."),
    )
    state = load_planning_state(repo_root, planning_state_path(mig_root))
    stdout_path = planning_stage_stdout_path(mig_root, "final-review")
    stdout_path.write_text(
        "final-decision: approve-auto - ready\n",
        encoding="utf-8",
    )
    state = complete_planning_step(
        state,
        "final-review",
        "approve-auto",
        {"stdout": stdout_path.relative_to(repo_root).as_posix()},
        completed_at=now,
        final_reason="ready",
    )
    save_planning_state(state, planning_state_path(mig_root), repo_root=repo_root)
    manifest = load_manifest(mig_root / "manifest.json")
    _refresh_manifest(manifest, mig_root / "manifest.json", status="ready")
    _commit_all(repo_root, "seed ready snapshot")


def _phase_doc(precondition: str, definition_of_done: str) -> str:
    return (
        f"## Precondition\n\n{precondition}\n\n"
        f"## Definition of Done\n\n{definition_of_done}\n"
    )



def _base_responses() -> list[tuple[str, dict[str, str]]]:
    """First 4 stages (approaches → review with no findings)."""
    return [
        (
            "Generated 2 approaches\n",
            {"approaches/incremental.md": "# Incremental\nStep by step approach."},
        ),
        ("Chose incremental approach.\n", {}),
        (
            "Plan expanded.\n",
            {
                "plan.md": "# Migration Plan\nPhased approach.",
                "phase-0-setup.md": _phase_doc("always", "Setup scaffolding is in place."),
                "phase-1-migrate.md": _phase_doc(
                    "phase 0 complete",
                    "Core migration lands cleanly and validation passes.",
                ),
            },
        ),
        ("Reviewed plan. no findings.\n", {}),
    ]


# ---------------------------------------------------------------------------
# one-step planning
# ---------------------------------------------------------------------------


def test_successful_step_publishes_docs_and_state_together(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root, live_dir, mig_root = _planning_repo_context(tmp_path, monkeypatch)

    result, mock = _run_next_step(
        repo_root,
        live_dir,
        [
            _workspace_response(
                "Generated 2 approaches\n",
                {"approaches/incremental.md": "# Incremental\n"},
            )
        ],
        monkeypatch,
    )

    assert result.status == "published"
    assert result.step == "approaches"
    assert result.next_step == "pick-best"
    assert result.terminal_outcome is None
    assert mock.stage_labels == ["approaches"]
    assert mock.migration_dirs[0] != mig_root

    manifest = load_manifest(mig_root / "manifest.json")
    state = load_planning_state(repo_root, planning_state_path(mig_root))
    assert manifest.status == "planning"
    assert state.next_step == "pick-best"
    assert [step.name for step in state.completed_steps] == ["approaches"]
    assert (mig_root / "approaches" / "incremental.md").is_file()
    assert planning_stage_stdout_path(mig_root, "approaches").read_text(
        encoding="utf-8"
    ) == "Generated 2 approaches\n"


def test_failed_step_does_not_publish_partial_docs_or_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root, live_dir, mig_root = _planning_repo_context(tmp_path, monkeypatch)
    _seed_planning_snapshot(
        repo_root,
        live_dir,
        [
            ("approaches", "completed", "Generated approaches.\n"),
            ("pick-best", "completed", "Chose incremental.\n"),
        ],
    )
    before = snapshot_tree_digest(mig_root)

    with pytest.raises(ContinuousRefactorError, match="planning.expand failed"):
        _run_next_step(
            repo_root,
            live_dir,
            [
                _workspace_response(
                    "bad expansion\n",
                    {"plan.md": "# Partial bad plan\n"},
                    returncode=1,
                )
            ],
            monkeypatch,
        )

    assert snapshot_tree_digest(mig_root) == before
    assert not (mig_root / "plan.md").exists()
    assert not planning_stage_stdout_path(mig_root, "expand").exists()
    assert load_planning_state(repo_root, planning_state_path(mig_root)).next_step == "expand"


def test_resume_skips_completed_steps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root, live_dir, mig_root = _planning_repo_context(tmp_path, monkeypatch)
    _seed_planning_snapshot(
        repo_root,
        live_dir,
        [
            ("approaches", "completed", "Generated approaches.\n"),
            ("pick-best", "completed", "Chose incremental.\n"),
        ],
    )

    result, mock = _run_next_step(
        repo_root,
        live_dir,
        [
            _workspace_response(
                "Expanded.\n",
                {
                    "plan.md": "# Plan\n",
                    "phase-0-setup.md": _phase_doc("always", "Setup is complete."),
                },
            )
        ],
        monkeypatch,
    )

    assert result.status == "published"
    assert mock.stage_labels == ["expand"]
    state = load_planning_state(repo_root, planning_state_path(mig_root))
    assert [step.name for step in state.completed_steps] == [
        "approaches",
        "pick-best",
        "expand",
    ]
    assert state.next_step == "review"


def test_revise_path_records_review_findings_as_planning_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root, live_dir, mig_root = _planning_repo_context(tmp_path, monkeypatch)
    _seed_planning_snapshot(
        repo_root,
        live_dir,
        [
            ("approaches", "completed", "Generated approaches.\n"),
            ("pick-best", "completed", "Chose incremental.\n"),
            ("expand", "completed", "Expanded.\n"),
        ],
        plan_text="# Plan v1\n",
        phase_text=_phase_doc("always", "Setup is complete."),
    )

    result, mock = _run_next_step(
        repo_root,
        live_dir,
        [_workspace_response("1. Missing rollback step.\n", {})],
        monkeypatch,
    )

    state = load_planning_state(repo_root, planning_state_path(mig_root))
    assert result.status == "published"
    assert mock.stage_labels == ["review"]
    assert state.next_step == "revise"
    assert state.review_findings == "live/rework-auth/.planning/stages/review.stdout.md"
    assert planning_stage_stdout_path(mig_root, "review").read_text(
        encoding="utf-8"
    ) == "1. Missing rollback step.\n"


def test_review_two_findings_fail_without_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root, live_dir, mig_root = _planning_repo_context(tmp_path, monkeypatch)
    _seed_planning_snapshot(
        repo_root,
        live_dir,
        [
            ("approaches", "completed", "Generated approaches.\n"),
            ("pick-best", "completed", "Chose incremental.\n"),
            ("expand", "completed", "Expanded.\n"),
            ("review", "findings", "1. Missing rollback step.\n"),
            ("revise", "completed", "Revised.\n"),
        ],
        plan_text="# Plan v2\n",
        phase_text=_phase_doc("always", "Setup is complete."),
    )
    before = snapshot_tree_digest(mig_root)

    with pytest.raises(
        ContinuousRefactorError,
        match="planning.review-2 failed: revised plan still has findings",
    ):
        _run_next_step(
            repo_root,
            live_dir,
            [_workspace_response("1. Still broken.\n", {})],
            monkeypatch,
        )

    assert snapshot_tree_digest(mig_root) == before
    assert not planning_stage_stdout_path(mig_root, "review-2").exists()
    assert load_planning_state(repo_root, planning_state_path(mig_root)).next_step == "review-2"


def test_final_ready_rejects_inconsistent_manifest_docs_before_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root, live_dir, mig_root = _planning_repo_context(tmp_path, monkeypatch)
    _seed_planning_snapshot(
        repo_root,
        live_dir,
        [
            ("approaches", "completed", "Generated approaches.\n"),
            ("pick-best", "completed", "Chose incremental.\n"),
            ("expand", "completed", "Expanded.\n"),
            ("review", "clear", "no findings\n"),
        ],
        plan_text="# Plan\n",
        phase_text="## Precondition\n\nalways\n",
    )
    before = snapshot_tree_digest(mig_root)

    result, mock = _run_next_step(
        repo_root,
        live_dir,
        [_workspace_response("final-decision: approve-auto - solid\n", {})],
        monkeypatch,
    )

    assert result.status == "blocked"
    assert "workspace validation failed" in result.reason
    assert mock.stage_labels == ["final-review"]
    assert snapshot_tree_digest(mig_root) == before
    assert not planning_stage_stdout_path(mig_root, "final-review").exists()
    assert load_manifest(mig_root / "manifest.json").status == "planning"
    assert load_planning_state(repo_root, planning_state_path(mig_root)).next_step == "final-review"


def test_refine_planning_keeps_current_cursor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root, live_dir, mig_root = _planning_repo_context(tmp_path, monkeypatch)
    _seed_planning_snapshot(
        repo_root,
        live_dir,
        [
            ("approaches", "completed", "Generated approaches.\n"),
            ("pick-best", "completed", "Chose incremental.\n"),
        ],
    )

    result, mock = _run_refine_step(
        repo_root,
        live_dir,
        [
            _workspace_response(
                "Expanded with feedback.\n",
                {
                    "plan.md": "# Plan\n",
                    "phase-0-setup.md": _phase_doc("always", "Setup is complete."),
                },
            )
        ],
        monkeypatch,
        feedback="Add a smaller first phase.",
    )

    state = load_planning_state(repo_root, planning_state_path(mig_root))
    assert result.status == "published"
    assert result.step == "expand"
    assert mock.stage_labels == ["expand"]
    assert state.next_step == "review"
    assert state.feedback[-1].text == "Add a smaller first phase."


def test_refine_ready_reopen_runs_one_revise_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root, live_dir, mig_root = _planning_repo_context(tmp_path, monkeypatch)
    _seed_ready_snapshot(repo_root, live_dir)

    result, mock = _run_refine_step(
        repo_root,
        live_dir,
        [
            _workspace_response(
                "Revised with feedback.\n",
                {
                    "plan.md": "# Plan v2\n",
                    "phase-0-setup.md": _phase_doc("always", "Setup is complete."),
                },
            )
        ],
        monkeypatch,
        feedback="Narrow the rollout.",
    )

    manifest = load_manifest(mig_root / "manifest.json")
    state = load_planning_state(repo_root, planning_state_path(mig_root))
    assert result.status == "published"
    assert result.step == "revise"
    assert mock.stage_labels == ["revise"]
    assert manifest.status == "planning"
    assert state.next_step == "review-2"
    assert state.revision_base_step_counts == (5,)


def test_refine_repeated_steps_keep_original_stdout_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root, live_dir, mig_root = _planning_repo_context(tmp_path, monkeypatch)
    _seed_ready_snapshot(repo_root, live_dir)
    original_final_review = planning_stage_stdout_path(mig_root, "final-review")
    original_text = original_final_review.read_text(encoding="utf-8")

    result, _mock = _run_refine_step(
        repo_root,
        live_dir,
        [
            _workspace_response(
                "Revised with feedback.\n",
                {
                    "plan.md": "# Plan v2\n",
                    "phase-0-setup.md": _phase_doc("always", "Setup is complete."),
                },
            )
        ],
        monkeypatch,
    )
    assert result.status == "published"
    _commit_all(repo_root, "planning refine")

    for responses in (
        [_workspace_response("Reviewed revised plan. no findings.\n")],
        [_workspace_response("final-decision: approve-auto - refined ready\n")],
    ):
        result, _mock = _run_next_step(repo_root, live_dir, responses, monkeypatch)
        assert result.status == "published"
        _commit_all(repo_root, f"planning {result.step}")

    state = load_planning_state(repo_root, planning_state_path(mig_root))
    final_review_refs = [
        step.outputs["stdout"]
        for step in state.completed_steps
        if step.name == "final-review"
    ]
    assert final_review_refs == [
        "live/rework-auth/.planning/stages/final-review.stdout.md",
        "live/rework-auth/.planning/stages/final-review-2.stdout.md",
    ]
    assert original_final_review.read_text(encoding="utf-8") == original_text
    assert (
        mig_root / ".planning" / "stages" / "final-review-2.stdout.md"
    ).read_text(encoding="utf-8") == "final-decision: approve-auto - refined ready\n"


def test_refine_ready_can_reopen_after_prior_refine_cycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root, live_dir, mig_root = _planning_repo_context(tmp_path, monkeypatch)
    _seed_ready_snapshot(repo_root, live_dir)
    original_final_review = planning_stage_stdout_path(mig_root, "final-review")
    original_final_review_text = original_final_review.read_text(encoding="utf-8")

    result, _mock = _run_refine_step(
        repo_root,
        live_dir,
        [
            _workspace_response(
                "Revised with feedback.\n",
                {
                    "plan.md": "# Plan v2\n",
                    "phase-0-setup.md": _phase_doc("always", "Setup is complete."),
                },
            )
        ],
        monkeypatch,
        feedback="Narrow the rollout.",
    )
    assert result.status == "published"
    assert result.step == "revise"
    _commit_all(repo_root, "planning refine")

    for responses in (
        [_workspace_response("Reviewed revised plan. no findings.\n")],
        [_workspace_response("final-decision: approve-auto - refined ready\n")],
    ):
        result, _mock = _run_next_step(repo_root, live_dir, responses, monkeypatch)
        assert result.status == "published"
        _commit_all(repo_root, f"planning {result.step}")

    result, mock = _run_refine_step(
        repo_root,
        live_dir,
        [
            _workspace_response(
                "Revised again.\n",
                {
                    "plan.md": "# Plan v3\n",
                    "phase-0-setup.md": _phase_doc("always", "Setup is complete."),
                },
            )
        ],
        monkeypatch,
        feedback="Make the second pass smaller.",
    )

    state = load_planning_state(repo_root, planning_state_path(mig_root))
    assert result.status == "published"
    assert result.step == "revise"
    assert mock.stage_labels == ["revise"]
    assert state.next_step == "review-2"
    assert [feedback.text for feedback in state.feedback] == [
        "Narrow the rollout.",
        "Make the second pass smaller.",
    ]
    assert [step.name for step in state.completed_steps] == [
        "approaches",
        "pick-best",
        "expand",
        "review",
        "final-review",
        "revise",
        "review-2",
        "final-review",
        "revise",
    ]
    assert state.revision_base_step_counts == (5, 8)
    final_review_refs = [
        step.outputs["stdout"]
        for step in state.completed_steps
        if step.name == "final-review"
    ]
    assert final_review_refs == [
        "live/rework-auth/.planning/stages/final-review.stdout.md",
        "live/rework-auth/.planning/stages/final-review-2.stdout.md",
    ]
    assert original_final_review.read_text(encoding="utf-8") == original_final_review_text
    assert (
        mig_root / ".planning" / "stages" / "final-review-2.stdout.md"
    ).read_text(encoding="utf-8") == "final-decision: approve-auto - refined ready\n"
    assert (
        mig_root / ".planning" / "stages" / "revise.stdout.md"
    ).read_text(encoding="utf-8") == "Revised with feedback.\n"
    assert (
        mig_root / ".planning" / "stages" / "revise-2.stdout.md"
    ).read_text(encoding="utf-8") == "Revised again.\n"


# ---------------------------------------------------------------------------
# initial decisions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    (
        "decision",
        "reason",
        "status",
        "manifest_status",
        "awaiting",
        "phase_names",
        "should_skip",
    ),
    [
        ("approve-auto", "plan is solid", "ready", "ready", False, ("setup", "migrate"), False),
        (
            "approve-needs-human",
            "needs security audit",
            "awaiting_human_review",
            "ready",
            True,
            ("setup", "migrate"),
            False,
        ),
        ("reject", "fundamentally flawed approach", "skipped", "skipped", False, (), True),
    ],
)
def test_initial_decisions(
    decision: str,
    reason: str,
    status: str,
    manifest_status: str,
    awaiting: bool,
    phase_names: tuple[str, ...],
    should_skip: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir, mig_root = _planning_context(tmp_path, monkeypatch)
    outcome, mock, _ = _run_planning(
        tmp_path,
        live_dir,
        _base_responses() + [_planning_decision_response(decision, reason)],
        monkeypatch,
    )

    assert outcome == PlanningOutcome(status=status, reason=reason)

    manifest = load_manifest(mig_root / "manifest.json")
    assert manifest.status == manifest_status
    assert manifest.awaiting_human_review is awaiting
    if awaiting:
        assert manifest.human_review_reason == reason
    else:
        assert manifest.human_review_reason is None

    if should_skip:
        skip_file = mig_root / "intentional-skip.md"
        assert skip_file.exists()
        skip_content = skip_file.read_text(encoding="utf-8")
        assert _TARGET in skip_content
        assert reason in skip_content
    else:
        assert len(manifest.phases) == 2
        assert tuple(phase.name for phase in manifest.phases) == phase_names
        assert manifest.current_phase == phase_names[0]
        assert manifest.phases[0].precondition == "always"
        assert (mig_root / "plan.md").exists()
        assert (mig_root / "approaches" / "incremental.md").exists()
        assert (mig_root / "phase-0-setup.md").exists()
        assert (mig_root / "phase-1-migrate.md").exists()

    assert mock.call_count == 5


def test_no_findings_path_keeps_stage_order_and_context_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir, _ = _planning_context(tmp_path, monkeypatch)
    _, mock, _ = _run_planning(
        tmp_path,
        live_dir,
        _base_responses() + [_planning_decision_response("approve-auto", "plan is solid")],
        monkeypatch,
    )

    assert mock.stage_labels == [
        "approaches",
        "pick-best",
        "expand",
        "review",
        "final-review",
    ]
    assert "Approaches:\n### incremental\n# Incremental\nStep by step approach." in mock.prompts[1]
    assert "Chosen approach (from live/rework-auth/.planning/stages/pick-best.stdout.md):" in mock.prompts[2]
    assert "Chose incremental approach.\n" in mock.prompts[2]
    assert "Plan:\n# Migration Plan\nPhased approach." in mock.prompts[3]
    assert "Plan:\n# Migration Plan\nPhased approach." in mock.prompts[4]


def test_run_planning_persists_durable_stage_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir, mig_root = _planning_context(tmp_path, monkeypatch)
    _run_planning(
        tmp_path,
        live_dir,
        _base_responses() + [_planning_decision_response("approve-auto", "plan is solid")],
        monkeypatch,
    )

    state = load_planning_state(tmp_path, planning_state_path(mig_root))

    assert state.next_step == "terminal-ready"
    assert state.final_decision == "approve-auto"
    assert state.final_reason == "plan is solid"
    assert [step.name for step in state.completed_steps] == [
        "approaches",
        "pick-best",
        "expand",
        "review",
        "final-review",
    ]
    for step in state.completed_steps:
        stdout_ref = step.outputs["stdout"]
        assert stdout_ref.startswith("live/rework-auth/.planning/stages/")
        assert (tmp_path / stdout_ref).is_file()


def test_planning_context_reconstructs_from_durable_stage_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir, mig_root = _planning_context(tmp_path, monkeypatch)
    artifacts = _make_artifacts(tmp_path)
    transient_stdout = artifacts.root / "planning" / "pick-best" / "agent.stdout.log"
    transient_stdout.parent.mkdir(parents=True)
    transient_stdout.write_text("wrong transient output\n", encoding="utf-8")

    state = new_planning_state(_TARGET, now="2026-04-29T12:00:00.000+00:00")
    for name, text in (
        ("approaches", "Generated approaches.\n"),
        ("pick-best", "Chose incremental approach.\n"),
    ):
        stdout_path = planning_stage_stdout_path(mig_root, name)
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text(text, encoding="utf-8")
        state = complete_planning_step(
            state,
            name,
            "completed",
            {"stdout": stdout_path.relative_to(tmp_path).as_posix()},
            completed_at="2026-04-29T12:01:00.000+00:00",
        )
    save_planning_state(state, planning_state_path(mig_root), repo_root=tmp_path)
    shutil.rmtree(artifacts.root)

    context = _build_durable_planning_context(
        repo_root=tmp_path,
        live_dir=live_dir,
        migration_name=_MIGRATION,
        state=state,
    )

    assert "Chosen approach" in context
    assert "Chose incremental approach." in context
    assert ".planning/stages/pick-best.stdout.md" in context
    assert "wrong transient output" not in context
    assert "agent.stdout.log" not in context


# ---------------------------------------------------------------------------
# review findings trigger revise + review-2
# ---------------------------------------------------------------------------


def _revise_responses() -> list[tuple[str, dict[str, str]]]:
    """Approaches → expand → review-with-findings → revise → review-2."""
    return [
        (
            "Generated approach\n",
            {"approaches/big-bang.md": "# Big Bang\nAll at once."},
        ),
        ("Chose big-bang.\n", {}),
        (
            "Expanded.\n",
            {
                "plan.md": "# Plan v1",
                "phase-0-prep.md": _phase_doc("always", "Prep phase is complete."),
            },
        ),
        ("1. Missing rollback step.\n2. Phase order unclear.\n", {}),
        (
            "Revised plan.\n",
            {
                "plan.md": "# Plan v2 (revised)",
                "phase-0-prep.md": _phase_doc("always", "Revised prep is complete."),
                "phase-1-rollback.md": _phase_doc(
                    "phase 0 done",
                    "Rollback path exists and validation passes.",
                ),
            },
        ),
        ("Reviewed revised plan. no findings.\n", {}),
    ]


def test_review_findings_trigger_revise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir, mig_root = _planning_context(tmp_path, monkeypatch)
    outcome, mock, _ = _run_planning(
        tmp_path,
        live_dir,
        _revise_responses()
        + [_planning_decision_response("approve-auto", "revised plan looks good")],
        monkeypatch,
    )

    assert outcome.status == "ready"

    manifest = load_manifest(mig_root / "manifest.json")
    assert manifest.status == "ready"
    assert len(manifest.phases) == 2
    assert manifest.current_phase == "prep"
    assert manifest.phases[0].name == "prep"
    assert manifest.phases[1].name == "rollback"
    assert manifest.phases[1].precondition == "phase 0 done"

    assert (mig_root / "plan.md").read_text(encoding="utf-8") == "# Plan v2 (revised)"
    assert mock.call_count == 7


def test_revised_plan_is_reloaded_for_follow_up_reviews(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir, _ = _planning_context(tmp_path, monkeypatch)
    _, mock, _ = _run_planning(
        tmp_path,
        live_dir,
        _revise_responses()
        + [_planning_decision_response("approve-auto", "revised plan looks good")],
        monkeypatch,
    )

    review_two_prompt = mock.prompts[5]
    final_review_prompt = mock.prompts[6]

    assert "# Plan v2 (revised)" in review_two_prompt
    assert "# Plan v1" not in review_two_prompt
    assert "# Plan v2 (revised)" in final_review_prompt
    assert "# Plan v1" not in final_review_prompt


def test_revise_path_keeps_existing_prompt_stages_with_distinct_stage_labels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir, _ = _planning_context(tmp_path, monkeypatch)
    _, mock, _ = _run_planning(
        tmp_path,
        live_dir,
        _revise_responses()
        + [_planning_decision_response("approve-auto", "revised plan looks good")],
        monkeypatch,
    )

    assert mock.stage_labels == [
        "approaches",
        "pick-best",
        "expand",
        "review",
        "revise",
        "review-2",
        "final-review",
    ]
    assert (
        "You are a planning agent expanding the chosen approach into a detailed migration plan."
        in mock.prompts[4]
    )
    assert (
        "Review findings to address (from live/rework-auth/.planning/stages/review.stdout.md):"
        in mock.prompts[4]
    )
    assert "1. Missing rollback step.\n2. Phase order unclear.\n" in mock.prompts[4]
    assert "You are a planning reviewer examining a refactoring migration plan." in mock.prompts[5]
    assert "Plan (revised):\n# Plan v2 (revised)" in mock.prompts[5]


def test_review_two_findings_fail_before_final_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir, mig_root = _planning_context(tmp_path, monkeypatch)
    responses = _revise_responses()
    responses[5] = ("1. Still missing rollback validation.\n", {})

    with pytest.raises(
        ContinuousRefactorError,
        match="planning.review-2 failed: revised plan still has findings",
    ):
        _run_planning(tmp_path, live_dir, responses, monkeypatch)

    assert not planning_stage_stdout_path(mig_root, "review-2").exists()
    state = load_planning_state(tmp_path, planning_state_path(mig_root))
    assert state.next_step == "review-2"


def test_failed_final_review_output_is_not_durable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir, mig_root = _planning_context(tmp_path, monkeypatch)

    with pytest.raises(
        ContinuousRefactorError,
        match="planning.final-review failed: Final review produced no output",
    ):
        _run_planning(
            tmp_path,
            live_dir,
            _base_responses() + [("debug line without decision\n", {})],
            monkeypatch,
        )

    assert not planning_stage_stdout_path(mig_root, "final-review").exists()
    state = load_planning_state(tmp_path, planning_state_path(mig_root))
    assert state.next_step == "final-review"


def test_manifest_phase_discovery_refreshes_only_after_file_writing_stages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir, _ = _planning_context(tmp_path, monkeypatch)
    discover_calls: list[tuple[str, ...]] = []
    real_discover = _discover_phase_files

    def spy_discover(mig_root: Path) -> tuple[object, ...]:
        discover_calls.append(tuple(path.name for path in sorted(mig_root.glob("phase-*-*.md"))))
        return real_discover(mig_root)

    monkeypatch.setattr("continuous_refactoring.planning._discover_phase_files", spy_discover)

    _run_planning(
        tmp_path,
        live_dir,
        _revise_responses()
        + [_planning_decision_response("approve-auto", "revised plan looks good")],
        monkeypatch,
    )

    assert discover_calls == [
        ("phase-0-prep.md",),
        ("phase-0-prep.md", "phase-1-rollback.md"),
    ]


def test_refresh_manifest_initializes_and_repairs_current_phase_only_when_rediscovering(
    tmp_path: Path,
) -> None:
    mig_root = tmp_path / "live" / "repair-phase"
    mig_root.mkdir(parents=True)
    manifest_path = mig_root / "manifest.json"
    phase_doc = _phase_doc("always", "Phase is complete.")
    (mig_root / "phase-1-setup.md").write_text(phase_doc, encoding="utf-8")
    (mig_root / "phase-2-ship.md").write_text(phase_doc, encoding="utf-8")

    manifest = MigrationManifest(
        name="repair-phase",
        created_at="2026-04-28T00:00:00Z",
        last_touch="2026-04-28T00:00:00Z",
        wake_up_on=None,
        awaiting_human_review=False,
        human_review_reason=None,
        status="planning",
        current_phase="",
        phases=(),
    )
    save_manifest(manifest, manifest_path)

    manifest = _refresh_manifest(manifest, manifest_path, mig_root=mig_root)
    assert manifest.current_phase == "setup"
    assert tuple(phase.name for phase in manifest.phases) == ("setup", "ship")

    untouched = _refresh_manifest(manifest, manifest_path, status="ready")
    assert untouched.current_phase == "setup"

    repaired = _refresh_manifest(
        manifest, manifest_path, mig_root=mig_root, current_phase="missing"
    )
    assert repaired.current_phase == "setup"


def test_parse_final_decision_ignores_trailing_lines() -> None:
    decision, reason = _parse_final_decision(
        "\n".join(
            [
                "debug: planning done",
                "final-decision: approve-auto — trailing log noise tolerated",
                "temporary debug line from telemetry",
            ]
        )
    )

    assert decision == "approve-auto"
    assert reason == "trailing log noise tolerated"


def test_parse_final_decision_without_reason_defaults_to_decision() -> None:
    decision, reason = _parse_final_decision("final-decision: reject")

    assert decision == "reject"
    assert reason == "reject"


def test_parse_final_decision_with_no_valid_line_raises() -> None:
    with pytest.raises(ContinuousRefactorError, match="Final review produced no output"):
        _parse_final_decision("temporary debug line\nanother line")


def test_review_has_findings_prefers_no_findings_anywhere() -> None:
    assert _review_has_findings("1. issue list\nNo findings\n") is False
    assert _review_has_findings("analysis complete") is True
    assert _review_has_findings("   \n") is False


def test_discover_phase_files_orders_by_numeric_phase_number(tmp_path: Path) -> None:
    mig_root = tmp_path / "live" / "ordering"
    mig_root.mkdir(parents=True)

    (mig_root / "phase-10-final.md").write_text(
        _phase_doc("phase 10 complete", "Final phase complete."),
        encoding="utf-8",
    )
    (mig_root / "phase-2-middle.md").write_text(
        _phase_doc("phase 1 complete", "Middle phase complete."),
        encoding="utf-8",
    )
    (mig_root / "phase-1-start.md").write_text(
        _phase_doc("always", "Start phase complete."),
        encoding="utf-8",
    )

    phases = _discover_phase_files(mig_root)

    assert tuple(phase.name for phase in phases) == ("start", "middle", "final")
    assert tuple(phase.precondition for phase in phases) == (
        "always",
        "phase 1 complete",
        "phase 10 complete",
    )


def test_discover_phase_files_falls_back_when_precondition_is_missing(
    tmp_path: Path,
) -> None:
    mig_root = tmp_path / "live" / "fallback"
    mig_root.mkdir(parents=True)

    (mig_root / "phase-1-legacy.md").write_text(
        "## Ready When\n\nLegacy completion wording.\n",
        encoding="utf-8",
    )

    phases = _discover_phase_files(mig_root)

    assert len(phases) == 1
    assert phases[0].precondition == "prerequisites in phase-1-legacy.md are met"


def test_discover_phase_files_reads_optional_effort_metadata(tmp_path: Path) -> None:
    mig_root = tmp_path / "live" / "effort"
    mig_root.mkdir(parents=True)

    (mig_root / "phase-1-risky.md").write_text(
        (
            "required_effort: high\n"
            "effort_reason: touches routing and planning\n\n"
            + _phase_doc("always", "Risky phase complete.")
        ),
        encoding="utf-8",
    )

    phases = _discover_phase_files(mig_root)

    assert len(phases) == 1
    assert phases[0].required_effort == "high"
    assert phases[0].effort_reason == "touches routing and planning"


def test_discover_phase_files_prefers_section_metadata_over_legacy_lines(
    tmp_path: Path,
) -> None:
    mig_root = tmp_path / "live" / "section-precedence"
    mig_root.mkdir(parents=True)

    (mig_root / "phase-1-risky.md").write_text(
        (
            "precondition: legacy precondition\n"
            "required_effort: low\n"
            "effort_reason: legacy reason\n\n"
            "## Precondition\n\nsection precondition\n\n"
            "## Required Effort\n\nhigh with extra context\n\n"
            "## Effort Reason\n\nsection reason wins\n\n"
            "## Definition of Done\n\nDone.\n"
        ),
        encoding="utf-8",
    )

    phases = _discover_phase_files(mig_root)

    assert len(phases) == 1
    assert phases[0].precondition == "section precondition"
    assert phases[0].required_effort == "high"
    assert phases[0].effort_reason == "section reason wins"


def test_discover_phase_files_rejects_invalid_required_effort(tmp_path: Path) -> None:
    mig_root = tmp_path / "live" / "bad-effort"
    mig_root.mkdir(parents=True)

    (mig_root / "phase-1-risky.md").write_text(
        "required_effort: extreme\n\n" + _phase_doc("always", "Done."),
        encoding="utf-8",
    )

    with pytest.raises(ContinuousRefactorError, match="phase-1-risky.md"):
        _discover_phase_files(mig_root)



def test_discover_phase_files_rejects_duplicate_phase_names(tmp_path: Path) -> None:
    mig_root = tmp_path / "live" / "duplicate-names"
    mig_root.mkdir(parents=True)

    (mig_root / "phase-1-setup.md").write_text(
        _phase_doc("always", "First setup phase complete."),
        encoding="utf-8",
    )
    (mig_root / "phase-2-setup.md").write_text(
        _phase_doc("after setup", "Duplicate setup phase complete."),
        encoding="utf-8",
    )

    with pytest.raises(
        ContinuousRefactorError, match="Duplicate phase names are not allowed",
    ):
        _discover_phase_files(mig_root)
