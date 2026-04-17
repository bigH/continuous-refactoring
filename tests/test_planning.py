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
    intentional_skips_dir,
    load_manifest,
    migration_root,
)
from continuous_refactoring.planning import (
    _parse_final_decision,
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
        self.prompts: list[str] = []

    def __call__(self, **kwargs: object) -> CommandCapture:
        assert self._index < len(self._responses), (
            f"Unexpected agent call #{self._index + 1}"
        )
        stdout, writes = self._responses[self._index]
        self._index += 1
        self.call_count += 1
        self.prompts.append(str(kwargs["prompt"]))

        for rel_path, content in writes.items():
            full = self._mig_root / rel_path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")

        stdout_path = Path(str(kwargs["stdout_path"]))
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
                "phase-0-setup.md": "Ready when: always\nSetup scaffolding.",
                "phase-1-migrate.md": "Ready when: phase 0 complete\nCore migration.",
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

    if should_skip:
        skip_file = intentional_skips_dir(live_dir) / f"{_MIGRATION}.md"
        assert skip_file.exists()
        skip_content = skip_file.read_text(encoding="utf-8")
        assert _TARGET in skip_content
        assert reason in skip_content
    else:
        assert len(manifest.phases) == 2
        assert tuple(phase.name for phase in manifest.phases) == phase_names
        assert manifest.phases[0].ready_when == "always"
        assert (mig_root / "plan.md").exists()
        assert (mig_root / "approaches" / "incremental.md").exists()
        assert (mig_root / "phase-0-setup.md").exists()
        assert (mig_root / "phase-1-migrate.md").exists()

    assert mock.call_count == 5


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
                "phase-0-prep.md": "Ready when: always\nPrep phase.",
            },
        ),
        ("1. Missing rollback step.\n2. Phase order unclear.\n", {}),
        (
            "Revised plan.\n",
            {
                "plan.md": "# Plan v2 (revised)",
                "phase-0-prep.md": "Ready when: always\nRevised prep.",
                "phase-1-rollback.md": "Ready when: phase 0 done\nRollback added.",
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
    assert manifest.phases[0].name == "prep"
    assert manifest.phases[1].name == "rollback"
    assert manifest.phases[1].ready_when == "phase 0 done"

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
        "Ready when: phase 10 complete\nFinal phase.",
        encoding="utf-8",
    )
    (mig_root / "phase-2-middle.md").write_text(
        "Ready when: phase 1 complete\nMiddle phase.",
        encoding="utf-8",
    )
    (mig_root / "phase-1-start.md").write_text(
        "Ready when: always\nStart phase.",
        encoding="utf-8",
    )

    phases = _discover_phase_files(mig_root)

    assert tuple(phase.name for phase in phases) == ("start", "middle", "final")
