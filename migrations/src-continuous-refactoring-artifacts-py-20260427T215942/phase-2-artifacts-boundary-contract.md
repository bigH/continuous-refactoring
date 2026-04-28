# Phase 2: Artifacts module in-place boundary hardening

## Objective
Create a strict, low-churn boundary contract in `artifacts.py` around artifact writes and serialization paths, preserving underlying exceptions through nested causes.

## Scope
- `src/continuous_refactoring/artifacts.py`
- `tests/test_continuous_refactoring.py`

## Instructions
1. Add private helpers in `artifacts.py` to isolate unsafe effects:
   - event append helper that captures and wraps effect-level `OSError` exceptions with `ContinuousRefactorError` using `from`.
   - summary serialization helper that wraps serialization/value-shape failures with `ContinuousRefactorError` using `from` when boundary context adds signal.
   - atomic write helper that wraps parent-dir/temp-file/write/replace failures with `ContinuousRefactorError` using `from`.
2. Use those helpers in:
   - `RunArtifacts.log()` event emission,
   - `RunArtifacts.write_summary()`,
   - `create_run_artifacts()` initialization where the first summary write establishes the run boundary state.
3. Add boundary-level context only where it changes caller signal (what failed and where), but do not replace clearer native errors from pure bookkeeping branches.
4. Keep existing module surface (`__all__`, class names, public functions) unchanged.
5. Update tests to pin that nested causes are preserved for event-write, summary-serialization, and atomic-write boundary failures.

## Precondition
- Phase 1 is marked complete in the migration manifest.
- `src/continuous_refactoring/artifacts.py` has not been edited yet in this migration.

## Definition of Done
- Boundary helper functions exist in `artifacts.py` and are wired into event-write and summary-write/serialize flows.
- Wrapped boundary failures from `artifacts.py` include original exceptions as `__cause__`.
- Paths that are semantically better left unwrapped remain unwrapped.
- `tests/test_continuous_refactoring.py` contains explicit cause assertions for artifact boundary failures.
- Public module contracts (`__all__`, types, API names, and `ContinuousRefactorError`) remain unchanged.

## Validation steps
- `uv run pytest tests/test_continuous_refactoring.py`
