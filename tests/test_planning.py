from __future__ import annotations

from pathlib import Path

import pytest

from continuous_refactoring.artifacts import (
    CommandCapture,
    ContinuousRefactorError,
    RunArtifacts,
    create_run_artifacts,
)
from continuous_refactoring.migrations import (
    MigrationManifest,
    intentional_skips_dir,
    load_manifest,
    migration_root,
    save_manifest,
)
from continuous_refactoring.planning import (
    _parse_final_decision,
    _refresh_manifest,
    _review_has_findings,
    _discover_phase_files,
    PlanningOutcome,
    run_planning,
)


_TASTE = "- Prefer deletion over wrapping.\n- Fail fast at boundaries."
_TARGET = "Rework auth module for clarity"
_MIGRATION = "rework-auth"


def _planning_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmpdir"))
    (tmp_path / "tmpdir").mkdir()

    live_dir = tmp_path / "live"
    live_dir.mkdir()
    mig_root = migration_root(live_dir, _MIGRATION)
    return live_dir, mig_root


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

    outcome = run_planning(
        _MIGRATION, _TARGET, _TASTE, tmp_path, live_dir,
        _make_artifacts(tmp_path),
        agent="codex", model="fake", effort="low", timeout=None,
    )
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

        for rel_path, content in writes.items():
            full = self._mig_root / rel_path
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
        skip_file = intentional_skips_dir(live_dir) / f"{_MIGRATION}.md"
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
    assert "Chosen approach:\nChose incremental approach.\n" in mock.prompts[2]
    assert "Plan:\n# Migration Plan\nPhased approach." in mock.prompts[3]
    assert "Plan:\n# Migration Plan\nPhased approach." in mock.prompts[4]


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
    assert "Review findings to address:\n1. Missing rollback step.\n2. Phase order unclear.\n" in mock.prompts[4]
    assert "You are a planning reviewer examining a refactoring migration plan." in mock.prompts[5]
    assert "Plan (revised):\n# Plan v2 (revised)" in mock.prompts[5]


def test_review_two_findings_fail_before_final_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir, _ = _planning_context(tmp_path, monkeypatch)
    responses = _revise_responses()
    responses[5] = ("1. Still missing rollback validation.\n", {})

    with pytest.raises(
        ContinuousRefactorError,
        match="planning.review-2 failed: revised plan still has findings",
    ):
        _run_planning(tmp_path, live_dir, responses, monkeypatch)


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
