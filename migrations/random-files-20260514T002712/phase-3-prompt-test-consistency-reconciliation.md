# Phase 3: Prompt/Test Consistency Reconciliation

required_effort: low
effort_reason: Scope is narrowly constrained to contract-alignment test updates with no planned production-path refactor.

## Goal
Align prompt and test invariants with the refactored boundary behavior so repository contracts remain explicit and accurate.

## Scope
- `tests/test_prompts.py`
- `tests/test_planning_publish.py`
- `tests/test_migration_tick.py` only when a Phase 2-equivalent behavior clarification requires assertion text/fixture alignment

## Out of Scope
- New feature work unrelated to boundary hardening
- Further structural refactors in migration boundary modules unless required for correctness discovered here
- Any source changes outside the explicit Scope file allowlist above

## Precondition
- Phases 1 and 2 are complete and published for this migration.
- Prompt/test contract files targeted in this phase still represent active migration semantics (including taste injection and planning publish expectations).
- No pending unresolved edits in this phase scope that would invalidate consistency verification.

## Implementation Instructions
1. Reconcile assertions and fixtures with the post-refactor behavior, keeping contracts strict and intention-revealing.
2. Confirm `## Taste`-injection expectations remain enforced where required.
3. Update tests only for legitimate contract alignment; do not loosen checks to mask behavioral regressions.
4. Keep edits minimal and scoped to the explicit file allowlist in Scope.

## Validation Steps
1. Run focused prompt/planning publish tests after edits.
2. Run the full configured validation command: `uv run pytest`.
3. Confirm no new inconsistency between documented migration semantics and enforced tests.

## Definition of Done
- Only files listed in Scope are modified in this phase.
- Prompt/test suites accurately reflect active migration boundary semantics after refactor.
- Required taste-related prompt invariants remain enforced.
- No assertion weakening that would hide real regressions.
- `uv run pytest` passes.
