# Phase 3: targeting git enumeration boundary hardening

## Objective
Standardize failure handling for tracked-file enumeration so git subprocess failures are wrapped at the targeting boundary with preserved causes.

## Scope
- `src/continuous_refactoring/targeting.py`
- `src/continuous_refactoring/git.py`
- `tests/test_targeting.py`

## Instructions
1. In `targeting.py`, replace direct subprocess-based tracked-file reads inside `list_tracked_files()` with the repository git boundary (`continuous_refactoring.git.run_command`, imported or module-qualified).
2. Add module-local context when git enumeration fails and preserve the original exception via `from` (`ContinuousRefactorError` nesting).
3. Keep non-fatal semantics for missing matches:
   - no patterns -> empty tuple
   - zero tracked files in matching mode -> empty tuple
4. Add/extend tests in `tests/test_targeting.py` for nested-cause behavior and message preservation when git enumeration fails.
5. Keep `list_tracked_files` return value and shape stable when git succeeds.

## Precondition
- Phase 2 is marked complete in the migration manifest.
- `rg -n \"def _parse_paths_arg\\(\" src/continuous_refactoring/loop.py` returns no matches, confirming Phase 2 removed loop-local path parsing.
- `rg -n \"parse_paths_arg\\(\" src/continuous_refactoring/loop.py` reports only delegated usage from the shared target resolver.
- `rg -n \"def list_tracked_files\\(\" src/continuous_refactoring/targeting.py` finds the tracked-file enumeration implementation that this phase hardens.

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
- Confirm that a failing git enumeration path raises `ContinuousRefactorError` with the original cause (`GitCommandError` from the git command boundary) where applicable.
- Confirm by inspection that tracked-file reads now flow through the repository git command boundary and no duplicate subprocess paths exist in `targeting.py`.
