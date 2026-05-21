# Phase 1: Contract Regression Net

## Goal
Capture and lock currently expected externally visible behavior for random-targeted surfaces before cleanup begins.

## Scope
- Test files under `tests/` that exercise random-targeted user-visible behavior.
- Planning artifact update that records exactly which contracts are locked in this phase.
- No production behavior changes.

## Precondition
- Migration status is `in-progress` and this phase is the manifest `current_phase`.
- No earlier migration phase is incomplete.
- A contract inventory artifact exists at `phase-1-contract-inventory.md` and lists the concrete behaviors this phase will lock.

## Implementation Instructions
1. Build/update `phase-1-contract-inventory.md` with explicit contract bullets (surface, expected behavior, and where it is asserted).
2. Add or tighten outcome-based regression tests for each listed contract.
3. Prefer existing fixtures and real collaborators; avoid mock-heavy interaction assertions.
4. Keep assertions strict enough to detect interface drift in CLI behavior, planning/migration artifact behavior, and other scoped observable outcomes.

## Validation Steps
1. Run focused tests updated for the listed contracts.
2. Demonstrate each new/updated contract test fails when its protected behavior is intentionally broken.
3. Run the configured full validation command.

## Definition of Done
- `phase-1-contract-inventory.md` exists and maps each scoped contract to specific regression coverage.
- Regression tests for listed contracts pass in the intended implementation.
- Evidence was collected during execution that intentionally breaking each protected behavior causes the corresponding test to fail.
- The full configured validation command passes.

required_effort: low
effort_reason: Focused test and artifact work with bounded code movement.
