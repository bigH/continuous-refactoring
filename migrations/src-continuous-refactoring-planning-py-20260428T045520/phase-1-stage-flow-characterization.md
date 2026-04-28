# Phase 1: Stage Flow Characterization

## Objective
Pin the current planning-stage behavior in tests before changing `run_planning()` structure.

## Scope
- `tests/test_planning.py`
- `src/continuous_refactoring/planning.py` only for behavior-neutral changes that expose already-existing outcomes to tests

## Instructions
1. Audit the current planning tests against the live `run_planning()` flow.
2. Add or tighten characterization coverage for the exact stage order and for which disk-backed inputs each stage reads.
3. Verify the tests cover the conditional revise/review-2 branch, including the failure path where `review-2` findings stop the flow before `final-review`.
4. Verify the tests pin which stages rediscover phase files through `_touch_manifest(..., mig_root=...)` and which stages only bump manifest metadata.
5. Keep any production edit strictly semantics-preserving. No helper extraction, control-flow rewrites, or renames in this phase.

## Precondition
- `migrations/src-continuous-refactoring-planning-py-20260428T045520/plan.md` exists and names `approaches/stage-pipeline-tightening.md` as the chosen approach.
- `src/continuous_refactoring/planning.py` still contains the live planning orchestration for approaches, selection, expansion, review, final review, and the revise/review-2 branch.
- No phase in this migration is marked done in `manifest.json`.

## Definition of Done
- `tests/test_planning.py` verifies the ordered planning flow for the no-findings path and the revise path.
- `tests/test_planning.py` verifies `pick-best` reads approaches from `approaches/*.md` after the approaches stage writes them.
- `tests/test_planning.py` verifies `review` reads `plan.md` written by `expand`, and `review-2` plus `final-review` reread revised `plan.md` from disk after `revise`.
- `tests/test_planning.py` verifies the revise path uses the same prompt stages as today (`expand` for revise, `review` for review-2) while keeping distinct stage labels for artifacts/logging.
- `tests/test_planning.py` verifies manifest phase discovery refreshes only after file-writing planning stages and preserves current `current_phase` initialization/repair behavior.
- Any `planning.py` edit in this phase is only to expose existing outcomes to tests and does not change stage order, prompt contents, or manifest transitions.
- Full `uv run pytest` passes.
- The repository remains shippable.

## Validation
- Optional focused checks while iterating:
  `uv run pytest tests/test_planning.py -k "test_initial_decisions or test_review_findings_trigger_revise or test_revised_plan_is_reloaded_for_follow_up_reviews"`
- Optional focused checks while iterating:
  `uv run pytest tests/test_planning.py -k "test_review_two_findings_fail_before_final_review or test_discover_phase_files_orders_by_numeric_phase_number or test_discover_phase_files_reads_optional_effort_metadata"`
- Required phase gate: `uv run pytest`
