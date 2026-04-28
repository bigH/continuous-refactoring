# Phase 1: run-command failure contract (checked runs)

## Objective
Define and enforce the failure contract for checked subprocess runs in `run_command()` with error nesting and stable messages.

## Scope
- `src/continuous_refactoring/git.py`
- `tests/test_git.py`

## Instructions
1. Add `GitCommandError(ContinuousRefactorError)` to `src/continuous_refactoring/git.py` and include it in module `__all__`.
2. Update `run_command()` so the non-zero return path for `check=True` raises `GitCommandError`.
3. Ensure the raised exception includes the current message payload: command text, `stdout`, and `stderr`.
4. Preserve `check=False` behavior exactly: return the `CompletedProcess` object without raising.
5. Add focused tests in `tests/test_git.py` for:
   - a checked command that returns non-zero and raises `GitCommandError`.
   - same failure includes `__cause__` and command-level output details.
   - checked-to-unchecked behavior is unchanged when `check=False`.

## Precondition
- `tests/test_git.py` and `src/continuous_refactoring/git.py` match the current checked/unchecked behavior baseline.
- No code in `loop.py`/`phases.py` depends on new symbols yet.

## Definition of Done
- A `GitCommandError` exists in `src/continuous_refactoring/git.py`.
- `run_command()` maps checked command failures to `GitCommandError` with nested cause.
- Checked callers continue to fail on bad commands.
- Unchecked callers still return `CompletedProcess`.
- `uv run pytest tests/test_git.py` passes.

## Validation steps
- Run `uv run pytest tests/test_git.py`.
- Confirm no touched logic in `loop.py`, `phases.py`, or `routing` changed by necessity.
