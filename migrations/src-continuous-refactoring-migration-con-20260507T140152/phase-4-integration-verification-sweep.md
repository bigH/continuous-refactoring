# Phase 4: Integration Verification Sweep

## Objective
Verify that the refactored consistency engine preserves behavior across integration call paths and automation gates.

## Scope
- Files in scope:
  - Integration-focused tests touching consistency usage, such as:
    - `tests/test_migration_tick.py`
    - `tests/test_migration_cli.py`
    - `tests/test_review_cli.py`
    - `tests/test_planning_publish.py`
  - Additional targeted tests only where behavior confidence is missing.
- No intended production behavior changes in this phase; verification-first.

## Precondition
- Phases 1–3 are complete.
- Refactored `migration_consistency` internals are stable and all direct module tests pass.
- Consistency call sites still route through existing public APIs.

## Implementation Instructions
1. Audit current integration coverage for consistency-gated behavior.
2. Add narrow tests where cross-module behavior was previously implicit.
3. Prefer example-based integration assertions on outcomes (blocking vs non-blocking, visibility behavior, readiness gates).
4. Avoid altering production logic unless a true regression is found.

## Validation
1. Run targeted integration suites affected by consistency consumers.
2. Run full configured validation command before marking complete.

## Definition of Done
- Integration paths depending on migration consistency checks have explicit, passing coverage for expected outcomes.
- No user-visible behavior drift is introduced by the refactor.
- Full configured validation command passes.

required_effort: low
effort_reason: Primarily validation and focused test additions with minimal production edits.
