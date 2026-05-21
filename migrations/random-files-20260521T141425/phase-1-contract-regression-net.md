# Phase 1: Contract Regression Net

## Goal
Capture and lock current externally visible behavior in focused regression tests for the random-file surfaces touched by this migration.

## Scope
- Tests only.
- Files under `tests/` that exercise selected random-file contracts (CLI behavior, migration/planning artifact behavior, and other user-observable outcomes touched by this migration target).
- No production behavior changes in this phase.

## Precondition
- Migration status is `in-progress` and this phase is the manifest `current_phase`.
- No earlier migration phase is incomplete.
- The random-target file set for this migration is still the intended scope, and the target contracts to lock are identifiable in current code/tests.

## Implementation Instructions
1. Identify externally visible behaviors in the random-targeted surfaces that later cleanup could accidentally change.
2. Add or tighten outcome-based regression tests for those behaviors.
3. Prefer real collaborators and filesystem/git fixtures already used by the suite; avoid interaction-call assertions and unnecessary mocks.
4. Keep assertions precise enough to catch interface drift, especially around CLI outputs/errors and planning/migration artifact semantics.

## Validation Steps
1. Run the focused tests added/updated for this phase.
2. Run the configured full validation command for the repository.

## Definition of Done
- A focused regression net exists for the random-targeted externally visible behaviors that this migration may affect.
- Added/updated tests fail when the protected behavior is intentionally broken and pass in the intended implementation.
- The full configured validation command passes.

required_effort: low
effort_reason: Adding focused regression coverage is bounded and low-risk.
