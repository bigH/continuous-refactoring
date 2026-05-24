# Phase 1: Contract Regression Net

## Goal
Lock currently expected externally visible behavior for random-targeted surfaces before internal cleanup starts.

## Scope
- Only tests under `tests/` that assert behavior of random-targeted user-facing surfaces (CLI behavior, repo-written artifacts, workflow outputs).
- Create/update one inventory artifact: `phase-1-contract-inventory.md`.
- Random-targeted surfaces in this migration are anchored to:
  - `src/continuous_refactoring/__main__.py`
  - `tests/test_main_entrypoint.py`
  - `LICENSE`
- No production source edits beyond minimal changes strictly required to make missing behavior observable in tests.

## Precondition
- Migration status is `ready` or `in-progress`, and this phase is the manifest `current_phase`.
- No earlier migration phase is incomplete.
- The random-targeted files for this migration still exist at the anchored paths listed in Scope.

## Implementation Instructions
1. Create or update `phase-1-contract-inventory.md` with explicit contract bullets: surface, expected behavior, and asserting test location.
2. Add or tighten outcome-based regression tests for every listed contract.
3. Prefer real collaborators and existing fixtures; avoid interaction-level mocks unless boundary isolation is necessary.
4. Keep assertions strict enough to detect interface drift in scoped observable outcomes.

## Validation Steps
1. Run focused tests that cover the listed contracts.
2. For each listed contract, intentionally break the behavior and verify the corresponding test fails.
3. Run the configured full validation command.

## Definition of Done
- `phase-1-contract-inventory.md` exists and maps each scoped contract to concrete regression coverage.
- Every contract listed in that inventory has passing outcome-based regression coverage.
- Execution evidence shows each listed contract test fails when its protected behavior is intentionally broken.
- The full configured validation command passes.

required_effort: low
effort_reason: Bounded, test-first contract capture with minimal production churn.
