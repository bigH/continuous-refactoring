# Phase 1: Boundary Contract Tests

## Goal
Lock externally visible boundary behavior for migration discovery, eligibility, and boundary error handling before structural refactoring.

## Scope
- `src/continuous_refactoring/migrations.py`
- `src/continuous_refactoring/migration_tick.py`
- Targeted tests under `tests/` that exercise these boundaries

## Out of Scope
- Broad helper rewrites in production modules
- CLI parser/wiring changes
- Manifest schema redesign

## Precondition
- The migration is in planning/execution order with no unresolved earlier phase for this migration.
- Boundary modules and their current externally observed contracts still exist (migration visibility filtering, eligibility selection, and boundary-level failure surfacing).
- The worktree is safe to edit for this migration scope (no conflicting in-progress edits in the same files for this migration run).

## Implementation Instructions
1. Identify current observable contracts at the module boundaries (inputs/outputs/errors), focusing on behavior that later refactors might accidentally change.
2. Add or strengthen tests that assert:
   - visible migration directory filtering behavior;
   - eligibility/candidate selection outcomes and ordering assumptions that are intended to remain stable;
   - boundary error translation/surfacing expectations (module-edge failures become expected error types/messages).
3. Prefer example-based tests for integration-heavy behavior; avoid over-mocking and avoid asserting internal call sequences unless unavoidable.
4. Keep tests concise and intent-revealing; remove/replace weak assertions that only verify implementation details.

## Validation Steps
1. Run focused tests for touched modules first (specific test files and, if useful, narrowed test nodes).
2. Run the full configured validation command: `uv run pytest`.
3. If failures expose ambiguous legacy behavior, resolve ambiguity by tightening contract assertions before moving to refactor phases.

## Definition of Done
- New or updated tests cover all three boundary surfaces in this phase with at least one explicit assertion each:
  - visible migration directory filtering;
  - candidate eligibility/ordering behavior;
  - boundary error surfacing/translation behavior.
- For each covered surface, tests assert concrete externally observable outcomes (returned candidates/order, skipped/selected behavior, raised error type/message shape, or persisted manifest side effects where applicable).
- New/updated tests assert externally observable outcomes, not incidental internal structure.
- No production behavior changes are introduced beyond test hardening support.
- `uv run pytest` passes.
