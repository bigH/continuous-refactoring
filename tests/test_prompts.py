from __future__ import annotations

from pathlib import Path

import pytest

from continuous_refactoring.config import TASTE_CURRENT_VERSION, default_taste_text
from continuous_refactoring.effort import EffortBudget
from continuous_refactoring.migrations import MigrationManifest, PhaseSpec
from continuous_refactoring.prompts import (
    CLASSIFIER_PROMPT,
    CONTINUOUS_REFACTORING_STATUS_BEGIN,
    CONTINUOUS_REFACTORING_STATUS_END,
    DEFAULT_REFACTORING_PROMPT,
    PHASE_EXECUTION_PROMPT,
    PHASE_READY_CHECK_PROMPT,
    PLANNING_APPROACHES_PROMPT,
    PLANNING_EXPAND_PROMPT,
    PLANNING_FINAL_REVIEW_PROMPT,
    PLANNING_PICK_BEST_PROMPT,
    PLANNING_REVIEW_PROMPT,
    compose_full_prompt,
    compose_classifier_prompt,
    compose_interview_prompt,
    compose_phase_execution_prompt,
    compose_phase_ready_prompt,
    compose_planning_prompt,
    compose_taste_refine_prompt,
    compose_taste_upgrade_prompt,
)
from continuous_refactoring.targeting import Target


_TASTE = "- Prefer deletion over wrapping.\n- Fail fast at boundaries."

_PLANNING_STAGES = (
    "approaches",
    "pick-best",
    "expand",
    "review",
    "final-review",
)

_PLANNING_PROMPTS_THAT_MENTION_PLAN_MD = (
    PLANNING_PICK_BEST_PROMPT,
    PLANNING_EXPAND_PROMPT,
    PLANNING_REVIEW_PROMPT,
    PLANNING_FINAL_REVIEW_PROMPT,
)

_PLANNING_PROMPTS_THAT_MENTION_APPROACHES = (
    PLANNING_EXPAND_PROMPT,
    PLANNING_REVIEW_PROMPT,
    PLANNING_FINAL_REVIEW_PROMPT,
)

_TASTE_INJECTED_PROMPTS = (
    CLASSIFIER_PROMPT,
    PLANNING_APPROACHES_PROMPT,
    PLANNING_PICK_BEST_PROMPT,
    PLANNING_EXPAND_PROMPT,
    PLANNING_REVIEW_PROMPT,
    PLANNING_FINAL_REVIEW_PROMPT,
    PHASE_READY_CHECK_PROMPT,
    PHASE_EXECUTION_PROMPT,
)


def _target() -> Target:
    return Target(
        description="Clean up auth module",
        files=("src/auth.py", "src/auth_test.py"),
        scoping="Focus on dead code removal",
    )


def _manifest() -> MigrationManifest:
    return MigrationManifest(
        name="auth-cleanup",
        created_at="2025-01-01T00:00:00.000+00:00",
        last_touch="2025-01-02T00:00:00.000+00:00",
        wake_up_on=None,
        awaiting_human_review=False,
        status="in-progress",
        current_phase="migrate",
        phases=(
            PhaseSpec(name="prep", file="phase-0-prep.md", done=True, precondition="always"),
            PhaseSpec(
                name="migrate", file="phase-1-migrate.md",
                done=False, precondition="prep complete",
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Output contracts on prompt constants
# ---------------------------------------------------------------------------

def test_classifier_output_contract() -> None:
    assert "decision: cohesive-cleanup" in CLASSIFIER_PROMPT
    assert "decision: needs-plan" in CLASSIFIER_PROMPT


def test_refactoring_prompt_defers_commit_to_driver() -> None:
    assert "Do not create git commits yourself." in DEFAULT_REFACTORING_PROMPT
    assert "commit it immediately" not in DEFAULT_REFACTORING_PROMPT


def test_refactoring_prompt_has_status_block_contract() -> None:
    assert CONTINUOUS_REFACTORING_STATUS_BEGIN in DEFAULT_REFACTORING_PROMPT
    assert CONTINUOUS_REFACTORING_STATUS_END in DEFAULT_REFACTORING_PROMPT
    assert "commit_rationale:" in DEFAULT_REFACTORING_PROMPT
    assert "why the refactor" in DEFAULT_REFACTORING_PROMPT


def test_phase_execution_prompt_has_status_block_contract() -> None:
    assert CONTINUOUS_REFACTORING_STATUS_BEGIN in PHASE_EXECUTION_PROMPT
    assert CONTINUOUS_REFACTORING_STATUS_END in PHASE_EXECUTION_PROMPT


def test_final_review_output_contract() -> None:
    assert "final-decision: approve-auto" in PLANNING_FINAL_REVIEW_PROMPT
    assert "final-decision: approve-needs-human" in PLANNING_FINAL_REVIEW_PROMPT
    assert "final-decision: reject" in PLANNING_FINAL_REVIEW_PROMPT


def test_ready_check_output_contract() -> None:
    assert "ready: yes" in PHASE_READY_CHECK_PROMPT
    assert "ready: no" in PHASE_READY_CHECK_PROMPT
    assert "ready: unverifiable" in PHASE_READY_CHECK_PROMPT


def test_phase_ready_prompt_uses_precondition_terminology() -> None:
    assert "precondition" in PHASE_READY_CHECK_PROMPT.lower()
    assert "ready_when" not in PHASE_READY_CHECK_PROMPT


# ---------------------------------------------------------------------------
# Taste injection mentions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("prompt", _TASTE_INJECTED_PROMPTS)
def test_prompts_mention_taste_injection(prompt: str) -> None:
    lower = prompt.lower()
    assert "taste" in lower
    assert "injected by the caller" in lower


# ---------------------------------------------------------------------------
# Artifact locations in planning prompts
# ---------------------------------------------------------------------------

def test_approaches_prompt_mentions_approaches_dir() -> None:
    assert "approaches/<idea>.md" in PLANNING_APPROACHES_PROMPT


def test_planning_expand_prompt_mentions_precondition_and_definition_of_done() -> None:
    assert "## Precondition" in PLANNING_EXPAND_PROMPT
    assert "## Definition of Done" in PLANNING_EXPAND_PROMPT
    assert "Do not conflate them." in PLANNING_EXPAND_PROMPT


def test_planning_review_prompt_separates_precondition_and_definition_of_done() -> None:
    assert "precondition" in PLANNING_REVIEW_PROMPT
    assert "Definition of Done" in PLANNING_REVIEW_PROMPT
    assert "not conflated" in PLANNING_REVIEW_PROMPT


def test_planning_prompts_keep_baseline_green_out_of_phase_preconditions() -> None:
    assert "harness enforces" in PLANNING_EXPAND_PROMPT
    assert "Phase preconditions must not restate" in PLANNING_EXPAND_PROMPT
    assert "full test suite passes" in PLANNING_EXPAND_PROMPT
    assert "Definition of Done may still require" in PLANNING_EXPAND_PROMPT
    assert "baseline-green" in PLANNING_REVIEW_PROMPT
    assert "fresh validation" in PLANNING_FINAL_REVIEW_PROMPT
    assert "evidence" in PLANNING_FINAL_REVIEW_PROMPT


def test_phase_ready_prompt_does_not_make_fresh_test_evidence_human_review() -> None:
    assert "Do not treat missing" in PHASE_READY_CHECK_PROMPT
    assert "fresh test evidence" in PHASE_READY_CHECK_PROMPT
    assert "human-review blocker" in PHASE_READY_CHECK_PROMPT
    assert "ignore that clause" in PHASE_READY_CHECK_PROMPT
    assert "Use `ready: unverifiable` only" in PHASE_READY_CHECK_PROMPT


@pytest.mark.parametrize("prompt", _PLANNING_PROMPTS_THAT_MENTION_PLAN_MD)
@pytest.mark.parametrize("fragment", ("plan.md", "phase-<n>-<name>.md"))
def test_planning_prompts_reference_plan_artifacts(prompt: str, fragment: str) -> None:
    assert fragment in prompt


@pytest.mark.parametrize("prompt", _PLANNING_PROMPTS_THAT_MENTION_APPROACHES)
def test_planning_prompts_mention_approaches(prompt: str) -> None:
    assert "approaches/" in prompt


# ---------------------------------------------------------------------------
# compose_classifier_prompt
# ---------------------------------------------------------------------------

def test_classifier_contains_base_prompt() -> None:
    result = compose_classifier_prompt(_target(), _TASTE)
    assert CLASSIFIER_PROMPT in result


def test_classifier_contains_target_description() -> None:
    target = _target()
    result = compose_classifier_prompt(target, _TASTE)
    assert target.description in result


def test_classifier_contains_target_files() -> None:
    target = _target()
    result = compose_classifier_prompt(target, _TASTE)
    for f in target.files:
        assert f in result


def test_classifier_contains_taste() -> None:
    result = compose_classifier_prompt(_target(), _TASTE)
    assert _TASTE in result


def test_classifier_contains_scope() -> None:
    target = _target()
    result = compose_classifier_prompt(target, _TASTE)
    assert target.scoping is not None
    assert target.scoping in result


def test_classifier_omits_scope_when_absent() -> None:
    target = Target(description="test", files=())
    result = compose_classifier_prompt(target, _TASTE)
    assert "## Scope" not in result


def test_classifier_omits_blank_scope_text() -> None:
    target = Target(description="test", files=(), scoping="   ")
    result = compose_classifier_prompt(target, _TASTE)
    assert "## Scope" not in result


# ---------------------------------------------------------------------------
# compose_planning_prompt
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stage", _PLANNING_STAGES)
def test_planning_contains_migration_name(stage: str) -> None:
    result = compose_planning_prompt(stage, "auth-cleanup", _TASTE, "some context")
    assert "auth-cleanup" in result


@pytest.mark.parametrize("stage", _PLANNING_STAGES)
def test_planning_contains_taste(stage: str) -> None:
    result = compose_planning_prompt(stage, "mig", _TASTE, "ctx")
    assert _TASTE in result


@pytest.mark.parametrize("stage", _PLANNING_STAGES)
def test_planning_contains_context(stage: str) -> None:
    result = compose_planning_prompt(stage, "mig", _TASTE, "important context here")
    assert "important context here" in result


def test_taste_refine_prompt_preserves_current_version_header_by_default() -> None:
    taste_path = Path("/tmp/taste.md")
    settle_path = Path("/tmp/taste.md.done")

    result = compose_taste_refine_prompt(
        taste_path=taste_path,
        settle_path=settle_path,
        starting_taste=default_taste_text(),
    )

    assert str(taste_path) in result
    assert str(settle_path) in result
    assert default_taste_text().strip() in result
    assert f"'taste-scoping-version: {TASTE_CURRENT_VERSION}'" in result
    assert "Keep that header unless the user explicitly asks to change it." in result
    assert "Do not add one unless the user explicitly asks for it." not in result


def test_taste_upgrade_prompt_uses_target_version_for_legacy_upgrade() -> None:
    taste_path = Path("/tmp/taste.md")
    settle_path = Path("/tmp/taste.md.done")

    result = compose_taste_upgrade_prompt(
        taste_path=taste_path,
        settle_path=settle_path,
        existing_taste="",
        stored_version=None,
        target_version=2,
    )

    assert "version 2" in result


def test_taste_prompts_tell_agent_to_exit_after_settle() -> None:
    taste_path = Path("/tmp/taste.md")
    settle_path = Path("/tmp/taste.md.done")

    prompts = (
        compose_interview_prompt(taste_path, settle_path, None),
        compose_taste_refine_prompt(
            taste_path=taste_path,
            settle_path=settle_path,
            starting_taste=default_taste_text(),
        ),
        compose_taste_upgrade_prompt(
            taste_path=taste_path,
            settle_path=settle_path,
            existing_taste="- Legacy rule.\n",
            stored_version=None,
            target_version=TASTE_CURRENT_VERSION,
        ),
    )

    for prompt in prompts:
        assert "After writing" in prompt
        assert "exit immediately without any extra output" in prompt


def test_planning_final_review_has_output_contract() -> None:
    result = compose_planning_prompt("final-review", "mig", _TASTE, "ctx")
    assert "final-decision: approve-auto" in result
    assert "final-decision: approve-needs-human" in result
    assert "final-decision: reject" in result


def test_compose_full_prompt_includes_retry_context_heading() -> None:
    result = compose_full_prompt(
        base_prompt="base",
        taste=_TASTE,
        target=_target(),
        scope_instruction=None,
        validation_command="uv run pytest",
        attempt=2,
        retry_context="- Summary: validation failed after refactor",
    )

    assert "## Retry Context" in result
    assert "validation failed after refactor" in result


def test_compose_full_prompt_omits_blank_retry_context() -> None:
    result = compose_full_prompt(
        base_prompt="base",
        taste=_TASTE,
        target=_target(),
        scope_instruction=None,
        validation_command="uv run pytest",
        attempt=2,
        retry_context=" \n\t ",
    )

    assert "## Retry Context" not in result
    assert "Use this as focused context only." not in result


def test_planning_approaches_mentions_artifacts() -> None:
    result = compose_planning_prompt("approaches", "mig", _TASTE, "ctx")
    assert "approaches/" in result


def test_planning_prompt_includes_effort_budget_guidance() -> None:
    result = compose_planning_prompt(
        "expand",
        "mig",
        _TASTE,
        "ctx",
        effort_budget=EffortBudget(default_effort="medium", max_allowed_effort="high"),
    )

    assert "Valid effort labels: `low`, `medium`, `high`, `xhigh`." in result
    assert "Current run max allowed effort: `high`." in result
    assert "lowest safe `required_effort`" in result
    assert "wait for a future run" in result


def test_planning_prompts_describe_phase_effort_metadata() -> None:
    assert "required_effort: <label>" in PLANNING_EXPAND_PROMPT
    assert "effort_reason" in PLANNING_EXPAND_PROMPT
    assert "`low`, `medium`, `high`, `xhigh`" in PLANNING_EXPAND_PROMPT
    assert "lowest safe" in PLANNING_REVIEW_PROMPT
    assert "future run" in PLANNING_FINAL_REVIEW_PROMPT


def test_phase_prompts_include_required_effort_metadata() -> None:
    manifest = _manifest()
    phase = PhaseSpec(
        name="migrate",
        file="phase-1-migrate.md",
        done=False,
        precondition="prep complete",
        required_effort="high",
        effort_reason="cross-module risk",
    )

    ready_prompt = compose_phase_ready_prompt(phase, manifest, _TASTE)
    execute_prompt = compose_phase_execution_prompt(
        phase,
        manifest,
        _TASTE,
        "uv run pytest",
    )

    for prompt in (ready_prompt, execute_prompt):
        assert "Required effort: high" in prompt
        assert "Effort reason: cross-module risk" in prompt


def test_full_prompt_prefers_target_scope_over_scope_instruction() -> None:
    target = Target(
        description="foo",
        files=("src/foo.py",),
        scoping="module scope from target",
        model_override=None,
        effort_override=None,
    )
    result = compose_full_prompt(
        base_prompt="BASE-PROMPT",
        taste="taste",
        target=target,
        scope_instruction="scope instruction fallback",
        validation_command="uv run pytest",
        attempt=1,
    )

    assert "## Scope\nmodule scope from target" in result
    assert "## Scope\nscope instruction fallback" not in result


def test_full_prompt_uses_scope_instruction_when_target_scope_is_blank() -> None:
    target = Target(
        description="foo",
        files=("src/foo.py",),
        scoping="   ",
        model_override=None,
        effort_override=None,
    )
    result = compose_full_prompt(
        base_prompt="BASE-PROMPT",
        taste="taste",
        target=target,
        scope_instruction="scope instruction fallback",
        validation_command="uv run pytest",
        attempt=1,
    )

    assert "## Scope\nscope instruction fallback" in result
    assert "## Scope\n   " not in result


def test_full_prompt_omits_scope_section_without_scoping_or_instruction() -> None:
    target = Target(
        description="foo",
        files=(),
        scoping=None,
        model_override=None,
        effort_override=None,
    )
    result = compose_full_prompt(
        base_prompt="BASE-PROMPT",
        taste="taste",
        target=target,
        scope_instruction=None,
        validation_command="uv run pytest",
        attempt=1,
    )

    assert "## Scope" not in result


def test_full_prompt_omits_blank_target_files() -> None:
    target = Target(
        description="foo",
        files=("   ", "src/foo.py"),
        scoping=None,
        model_override=None,
        effort_override=None,
    )
    result = compose_full_prompt(
        base_prompt="BASE-PROMPT",
        taste="taste",
        target=target,
        scope_instruction=None,
        validation_command="uv run pytest",
        attempt=1,
    )

    assert "## Target Files\n-    " not in result
    assert "## Target Files\n- src/foo.py" in result


# ---------------------------------------------------------------------------
# compose_phase_ready_prompt
# ---------------------------------------------------------------------------

def test_phase_ready_contains_base_prompt() -> None:
    manifest = _manifest()
    result = compose_phase_ready_prompt(manifest.phases[1], manifest, _TASTE)
    assert PHASE_READY_CHECK_PROMPT in result


def test_phase_ready_contains_phase_name() -> None:
    manifest = _manifest()
    phase = manifest.phases[1]
    result = compose_phase_ready_prompt(phase, manifest, _TASTE)
    assert phase.name in result


def test_phase_ready_contains_phase_file() -> None:
    manifest = _manifest()
    phase = manifest.phases[1]
    result = compose_phase_ready_prompt(phase, manifest, _TASTE)
    assert phase.file in result


def test_phase_ready_contains_precondition() -> None:
    manifest = _manifest()
    phase = manifest.phases[1]
    result = compose_phase_ready_prompt(phase, manifest, _TASTE)
    assert phase.precondition in result
    assert "Precondition:" in result
    assert "Ready when:" not in result


def test_phase_ready_contains_manifest_name() -> None:
    manifest = _manifest()
    result = compose_phase_ready_prompt(manifest.phases[1], manifest, _TASTE)
    assert manifest.name in result
    assert "Current phase file: phase-1-migrate.md" in result
    assert "Current phase name: migrate" in result
    assert "Current phase:" not in result


def test_phase_ready_contains_output_contract() -> None:
    manifest = _manifest()
    result = compose_phase_ready_prompt(manifest.phases[1], manifest, _TASTE)
    assert "ready: yes" in result
    assert "ready: no" in result
    assert "ready: unverifiable" in result


def test_phase_ready_contains_taste() -> None:
    manifest = _manifest()
    result = compose_phase_ready_prompt(manifest.phases[1], manifest, _TASTE)
    assert f"## Taste\n{_TASTE}" in result


# ---------------------------------------------------------------------------
# compose_phase_execution_prompt
# ---------------------------------------------------------------------------

def test_phase_execution_contains_base_prompt() -> None:
    manifest = _manifest()
    result = compose_phase_execution_prompt(
        manifest.phases[1], manifest, _TASTE, "uv run pytest"
    )
    assert PHASE_EXECUTION_PROMPT in result


def test_phase_execution_contains_phase_name() -> None:
    manifest = _manifest()
    phase = manifest.phases[1]
    result = compose_phase_execution_prompt(phase, manifest, _TASTE, "uv run pytest")
    assert phase.name in result


def test_phase_execution_contains_phase_file() -> None:
    manifest = _manifest()
    phase = manifest.phases[1]
    result = compose_phase_execution_prompt(phase, manifest, _TASTE, "uv run pytest")
    assert phase.file in result


def test_phase_execution_contains_manifest_name() -> None:
    manifest = _manifest()
    result = compose_phase_execution_prompt(
        manifest.phases[1], manifest, _TASTE, "uv run pytest"
    )
    assert manifest.name in result
    assert "Current phase file: phase-1-migrate.md" in result
    assert "Current phase name: migrate" in result


def test_phase_execution_contains_taste() -> None:
    manifest = _manifest()
    result = compose_phase_execution_prompt(
        manifest.phases[1], manifest, _TASTE, "uv run pytest"
    )
    assert _TASTE in result


def test_phase_execution_contains_validation_command() -> None:
    manifest = _manifest()
    result = compose_phase_execution_prompt(
        manifest.phases[1], manifest, _TASTE, "uv run pytest -q"
    )

    assert "## Validation" in result
    assert "Run: `uv run pytest -q`" in result
    assert "Run the full configured validation command before declaring success." in result
    assert "Definition of Done" in result
    assert "A phase is done only when the Definition of Done is satisfied" in result


def test_phase_execution_includes_stripped_retry_context() -> None:
    manifest = _manifest()
    result = compose_phase_execution_prompt(
        manifest.phases[1],
        manifest,
        _TASTE,
        "uv run pytest",
        retry_context=" \nvalidation failed after phase execution\n ",
    )

    assert "## Retry Context\n\nvalidation failed after phase execution" in result
    assert "Use this as focused context only. Do not copy raw failure text into code." in result
