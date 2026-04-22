# Readiness / Execution Split

## Strategy

Split the two phase responsibilities into separate modules:

- `src/continuous_refactoring/phase_readiness.py`
  - `ReadyVerdict`
  - ready-check prompt execution
  - ready verdict parsing
- `src/continuous_refactoring/phase_execution.py`
  - `ExecutePhaseOutcome`
  - execution agent call
  - validation retry loop
  - rollback and manifest completion

Then update `routing_pipeline.py`, tests, and `__init__.py` exports to import from the new modules directly. Do not leave compatibility re-export shims in `phases.py`; either delete `phases.py` or leave it only if it still owns a meaningful shared phase concept.

This creates more meaningful FQNs, especially because readiness is a small precondition check while execution is a transactional edit/validate/persist loop.

## Tradeoffs

Pros:
- Clearer module boundaries and import names.
- `phase_readiness.py` becomes small and easy to reason about.
- Execution tests can focus on the heavier transaction behavior without readiness noise.
- Future changes to ready-check parsing are less likely to disturb execution retry logic.

Cons:
- Higher churn across tests that monkeypatch `continuous_refactoring.phases.*`.
- Touches `routing_pipeline.py`, `tests/test_loop_migration_tick.py`, `tests/test_focus_on_live_migrations.py`, `tests/test_no_driver_branching.py`, and package export uniqueness.
- Could be more file motion than value if the immediate pain is only `execute_phase()` length.
- No re-export shim means every callsite must move in the same commit.

## Estimated Phases

1. **Prepare import-safe tests**
   - Identify all imports and monkeypatch paths for `check_phase_ready`, `execute_phase`, `ReadyVerdict`, and `ExecutePhaseOutcome`.
   - Add missing outcome tests in `tests/test_phases.py` before moving code.
   - Validation: `uv run pytest tests/test_phases.py tests/test_loop_migration_tick.py tests/test_focus_on_live_migrations.py tests/test_no_driver_branching.py`.

2. **Move readiness**
   - Create `phase_readiness.py`.
   - Move ready verdict parsing and `check_phase_ready()`.
   - Update direct imports and monkeypatch paths.
   - Run the narrow validation set.

3. **Move execution**
   - Create `phase_execution.py`.
   - Move `ExecutePhaseOutcome`, execution helpers, and `execute_phase()`.
   - Update imports, monkeypatch paths, and `src/continuous_refactoring/__init__.py`.
   - Delete `phases.py` if empty.

4. **Final package check**
   - Run `uv run pytest`.
   - Import the package once to catch duplicate `__all__` exports.

## Risk Profile

Medium risk. The behavior can remain identical, but monkeypatch path drift is easy to miss and will create noisy test failures.

Main watch-outs:
- This project has a strict package uniqueness rule in `__init__.py`; moved symbols must not be exported twice.
- Do not keep `phases.py` as a re-export facade. The repo explicitly forbids re-export shims for refactors.
- Broad migration tests patch through `routing_pipeline`, not only the source module. Update those deliberately.

## Best Fit

Choose this if the desired outcome is better FQNs and stronger module boundaries. It is less attractive if the migration is meant to be a quick clarity pass on the current file.
