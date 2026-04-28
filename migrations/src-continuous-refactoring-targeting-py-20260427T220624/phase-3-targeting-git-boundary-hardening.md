# Phase 3: targeting git enumeration boundary hardening

## Objective
Standardize failure handling for tracked-file enumeration so git subprocess failures are wrapped at the targeting boundary with preserved causes.

## Scope
- `src/continuous_refactoring/targeting.py`
- `src/continuous_refactoring/git.py`
- `tests/test_targeting.py`

## Instructions
1. In `targeting.py`, replace direct subprocess-based tracked-file reads inside `list_tracked_files()` with the repository git boundary in `git.run_command(...)`.
2. Add module-local context when git enumeration fails and preserve the original exception via `from` (`ContinuousRefactorError` nesting).
3. Keep non-fatal semantics for missing matches:
   - no patterns -> empty tuple
   - zero tracked files in matching mode -> empty tuple
4. Add/extend tests in `tests/test_targeting.py` for nested-cause behavior and message preservation when git enumeration fails.
5. Keep `list_tracked_files` return value and shape stable when git succeeds.

## Precondition
- `uv run pytest tests/test_targeting.py tests/test_run_once_regression.py tests/test_run.py` passes after phase-2 behavior changes.
- `rg -n \"parse_paths_arg\\(\" src/continuous_refactoring/loop.py` reports only callsite usage, confirming runtime targets now flow through the boundary for all callers.
- `rg -n \"list_tracked_files\\(\" src/continuous_refactoring/targeting.py` resolves to exactly one implementation path.

## Definition of Done
- `list_tracked_files()` uses the git command boundary and wraps failures with nested context at the targeting boundary.
- No behavioral changes in successful pattern matching paths.
- `uv run pytest tests/test_targeting.py` passes.
- `rg -n \"subprocess\\.run\\(\" src/continuous_refactoring/targeting.py` returns no matches for tracked-file reads.
- `tests/test_targeting.py` has explicit assertions for:
  - `ContinuousRefactorError` raised on git command failures
  - original failure attached as `__cause__`

## Validation steps
- Run: `uv run pytest tests/test_targeting.py`
- Confirm that a failing git enumeration path raises `ContinuousRefactorError` with the original cause (`GitCommandError` from `git.run_command`) where applicable.
- Confirm by inspection that tracked-file reads now flow through `git.run_command` and no duplicate subprocess paths exist in `targeting.py`.
