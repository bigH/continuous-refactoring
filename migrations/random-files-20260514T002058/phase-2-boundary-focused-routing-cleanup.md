# Phase 2 — Boundary-Focused Routing Cleanup

required_effort: medium
effort_reason: Internal cleanup must preserve subtle boundary semantics while reducing repetition.

## Scope
- `src/continuous_refactoring/routing.py`
- Routing-focused tests under `tests/` that directly cover touched behavior

## Objectives
- Improve readability and local abstraction quality inside routing logic.
- Remove unnecessary repetition in classify parsing/error handling paths.
- Preserve boundary semantics: exception nesting signal and finished-call expectations.

## Precondition
- Phase 1 is complete.
- Contracts locked in Phase 1 still exist and are unchanged in intent.
- `routing.py` structure still contains the targeted repetition/error-handling hotspots this phase is meant to clean up.
- No active conflicting edits in routing boundary code paths.

## Implementation Instructions
1. Identify small, domain-meaningful abstractions that reduce duplication without hiding control flow.
2. Keep exception translation at module boundaries and preserve causal chains.
3. Delete dead/legacy branches uncovered by refactor when proven unused by tests.
4. Update/add tests to verify outcomes and boundary behavior, not call internals.

## Validation Steps
1. Run routing-focused targeted tests for touched behavior.
2. Run the configured full validation command.

## Definition of Done
- `routing.py` is measurably simpler in duplicated parse/error-handling paths.
- Boundary exception semantics and observable routing outcomes remain intact.
- No speculative interface changes were introduced.
- Configured full validation command passes.
