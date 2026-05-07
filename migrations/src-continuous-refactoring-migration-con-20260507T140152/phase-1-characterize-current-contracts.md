# Phase 1: Characterize Current Contracts

## Objective
Capture current `migration_consistency` behavior in focused tests before refactoring internals.

## Scope
- Files in scope:
  - `tests/test_migration_consistency.py`
  - Minimal fixture/test helpers only if necessary.
- Behavior to characterize:
  - Mode-specific finding gating.
  - Visible migration directory filtering, including symlink exclusion behavior.
  - Phase document section contract checks (`## Precondition`, `## Definition of Done`).
  - Duplicate phase document detection semantics.

## Precondition
- No earlier phase is required.
- `src/continuous_refactoring/migration_consistency.py` still exposes current public functions and finding structures used by existing tests.
- Migration workspace paths and test fixtures referenced by these tests are intact.

## Implementation Instructions
1. Add or refine focused tests that assert observable outcomes, not helper implementation details.
2. Prefer deterministic assertions on finding code/severity/mode/path semantics.
3. Keep fixtures small and local to the tested contract.
4. Avoid broad rewrites of unrelated tests.

## Validation
1. Run targeted tests:
- `uv run pytest tests/test_migration_consistency.py`
2. If helper fixtures impact adjacent suites, run affected targeted suites.
3. Run full configured validation command before marking complete.

## Definition of Done
- `tests/test_migration_consistency.py` explicitly captures the key current contracts required by later refactor phases.
- New/updated tests fail if those contracts regress.
- Full configured validation command passes.

required_effort: low
effort_reason: Primarily additive characterization tests with low structural risk.
