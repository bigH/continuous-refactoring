# Phase 1: Baseline failure-cause behavior on artifact and phase boundaries

## Objective
Create a failing-ready baseline for cause-preserving failure behavior without changing production code.

## Scope
- `tests/test_continuous_refactoring.py`
- `tests/test_phases.py`
- `tests/test_loop_migration_tick.py`

## Instructions
1. Add baseline tests in `tests/test_continuous_refactoring.py` for artifact persistence paths:
   - fail-fast behavior on malformed payload flows
   - boundary failures now asserting `__cause__` expectations only where behavior already depends on translation
2. Add baseline tests in `tests/test_phases.py` for readiness/phase parsing failure paths that already route through `ContinuousRefactorError`.
3. Add focused checks in `tests/test_loop_migration_tick.py` for artifact summary/failure text preservation and non-masked root causes.
4. Keep all production files untouched in this phase.

## Precondition
- `tests/test_continuous_refactoring.py`, `tests/test_phases.py`, and `tests/test_loop_migration_tick.py` are green on the branch before edits.
- No production files in the migration scope have been modified yet.
- The target migration scope is unchanged in production modules.

## Definition of Done
- New tests explicitly exercise baseline boundary-failure expectations for artifact and phase orchestration.
- No production files are edited.
- All phase-1 scope tests pass.
- The tree remains shippable with only baseline test changes.

## Validation steps
- `uv run pytest tests/test_continuous_refactoring.py`
- `uv run pytest tests/test_phases.py`
- `uv run pytest tests/test_loop_migration_tick.py`
