# Phase 4: Integration Verification Sweep

## Objective
Confirm the refactored consistency engine preserves behavior across integration call paths.

## Scope
- Files in scope:
  - `tests/test_migration_tick.py`
  - `tests/test_migration_cli.py`
  - `tests/test_review_cli.py`
  - `tests/test_planning_publish.py`
  - `tests/test_migration_consistency.py` (only if integration assertions require shared fixtures)
- Production code edits are out of scope unless a validated regression fix is required.

## Precondition
- Phases 1, 2, and 3 are complete.
- `src/continuous_refactoring/migration_consistency.py` still exposes the unchanged public consistency API used by integration callers.
- Integration caller modules (`migration_tick`, `migration_cli`, `review_cli`, `planning_publish`) still consume consistency findings via existing contracts.

## Implementation Instructions
1. Audit integration coverage for consistency-driven outcomes.
2. Add narrow, outcome-focused tests where behavior is still implicit.
3. Keep assertions centered on blocking vs non-blocking behavior and expected finding visibility semantics.
4. Avoid production changes unless needed to fix a demonstrated regression.

## Validation
1. Run targeted integration tests:
- `uv run pytest tests/test_migration_tick.py tests/test_migration_cli.py tests/test_review_cli.py tests/test_planning_publish.py`
2. Run full configured validation command before marking the phase complete.

## Definition of Done
- Integration paths that depend on consistency findings have explicit passing outcome coverage.
- Refactor introduces no behavior drift in integration consumers.
- No public interface changes are introduced.
- Full configured validation command passes.

required_effort: low
effort_reason: Primarily integration test hardening with minimal production risk.
