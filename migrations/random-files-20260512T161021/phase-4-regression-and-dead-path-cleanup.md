# Phase 4: Regression and Dead-Path Cleanup

## Scope
- Any touched files from Phases 2-3, limited to:
  - dead helper removal,
  - duplicate branch removal,
  - readability pass that does not alter external contracts.

## Goals
1. Remove remaining dead/legacy error-path scaffolding discovered during earlier phases.
2. Confirm the migration is stable under full regression.
3. Leave the repository in a shippable state with clearer failure-path maintenance surface.

## Precondition
- Phases 1 through 3 are complete.
- Candidate cleanup targets are proven unused by current runtime paths and covered tests.
- Cleanup changes remain within the scoped modules/tests already touched by this migration.

## Implementation Instructions
1. Remove obsolete helper paths, duplicated branches, or fallback logic made redundant by Phase 2 normalization and Phase 3 test updates.
2. Keep changes minimal and readability-driven; do not expand scope into unrelated structural refactors.
3. Re-check phase files for consistency with what was actually changed and adjust wording where needed.

## Validation Steps
1. Run targeted regression on touched suites:
   - `uv run pytest tests/test_git.py tests/test_phases.py tests/test_planning_publish.py`
2. Run full validation command:
   - `uv run pytest`

## Definition of Done
- Obsolete failure-path code introduced by legacy structure is removed where safe.
- Remaining boundary and test code is cohesive and easier to maintain without contract drift.
- Migration phase docs match the implemented state and intended scope.
- Full validation command `uv run pytest` passes.
