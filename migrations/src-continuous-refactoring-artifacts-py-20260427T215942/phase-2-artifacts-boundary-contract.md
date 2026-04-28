# Phase 2: Artifacts module in-place boundary hardening

## Objective
Create a strict, low-churn boundary contract in `artifacts.py` with narrow helpers that preserve underlying exceptions through nested causes.

## Scope
- `src/continuous_refactoring/artifacts.py`
- `tests/test_continuous_refactoring.py`

## Instructions
1. Add private helpers in `artifacts.py` to isolate unsafe effects:
   - text read helper that captures and wraps effect-level `OSError` exceptions with `ContinuousRefactorError` using `from`.
   - decode helper that wraps decoding/value-shape failures with `ContinuousRefactorError` using `from`.
   - atomic write helper that wraps write/replace failures with `ContinuousRefactorError` using `from`.
2. Use those helpers in:
   - `create_run_artifacts()` summary/event path setup,
   - artifact read/load callsites,
   - any command capture serialization flow.
3. Add boundary-level context only where it changes caller signal (what failed and where), but do not replace signal when bubbling would preserve meaning.
4. Keep existing module surface (`__all__`, class names, public functions) unchanged.
5. Update tests to pin that nested causes are preserved for read/parse/write boundary failures.

## Precondition
- Phase 1 complete and passing.
- `tests/test_continuous_refactoring.py` passes before edits.
- `src/continuous_refactoring/artifacts.py` has not been edited yet in this migration.

## Definition of Done
- Boundary helper functions exist in `artifacts.py` and are wired into write/read/serialize flows.
- Wrapped boundary failures from `artifacts.py` include original exceptions as `__cause__`.
- Paths that are semantically better left unwrapped remain unwrapped.
- `tests/test_continuous_refactoring.py` contains explicit cause assertions for artifact boundary failures.
- Public module contracts (`__all__`, types, API names, and `ContinuousRefactorError`) remain unchanged.

## Validation steps
- `uv run pytest tests/test_continuous_refactoring.py`
