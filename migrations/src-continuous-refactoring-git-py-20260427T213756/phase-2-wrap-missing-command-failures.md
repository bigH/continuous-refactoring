# Phase 2: wrap missing-command and system-level command failures

## Objective
Preserve boundary truth and diagnostics when git commands cannot spawn at all.

## Scope
- `src/continuous_refactoring/git.py`
- `tests/test_git.py`

## Instructions
1. Wrap `subprocess.run(...)` in `run_command()` with a `try/except` for `FileNotFoundError`.
2. Raise `GitCommandError` from the caught `FileNotFoundError` with a command-focused message and explicit command tuple included where helpful.
3. Keep all existing helper functions (`current_branch`, `get_head_sha`, etc.) behavior unchanged.
4. Add a `tests/test_git.py` case that simulates missing executable:
   - patch `subprocess.run` to raise `FileNotFoundError`.
   - assert `GitCommandError` is raised.
   - assert `exc.__cause__` is `FileNotFoundError`.

## Precondition
- Phase 1 complete and passing.
- No API contract changes outside `continuous_refactoring.git`.

## Definition of Done
- Missing binary invocation is translated by `run_command()` into `GitCommandError` with a chained cause.
- Successful command execution path is unaffected.
- Checked execution remains strict and unchecked execution remains permissive.
- `uv run pytest tests/test_git.py` passes.
- `continuous_refactoring.git` exports remain stable for callsites.

## Validation steps
- Run `uv run pytest tests/test_git.py`.
- Run `uv run pytest tests/test_scope_loop_integration.py::test_revert_to_restores_requested_head_and_removes_untracked`.
- Verify `src/continuous_refactoring/__init__.py` still imports/re-exports without collisions.
