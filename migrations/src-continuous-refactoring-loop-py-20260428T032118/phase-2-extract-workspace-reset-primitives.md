# Phase 2: Extract Workspace Reset Primitives

## Objective
Move preserved-workspace snapshot/restore and source-baseline reset into a focused internal module first, so the highest-risk filesystem side effects are isolated before the full retry engine moves.

## Scope
- `src/continuous_refactoring/refactor_attempts.py`
- `src/continuous_refactoring/loop.py`
- `tests/test_run.py`
- `tests/test_loop_migration_tick.py` if import ownership or preserved-state coverage needs adjustment

## Instructions
1. Create `src/continuous_refactoring/refactor_attempts.py`.
2. Move these symbols into the new module:
   - `_PreservedFile`
   - `_PreservedWorkspaceTree`
   - `_preserve_workspace_tree()`
   - `_reset_to_source_baseline()`
3. Keep the moved API internal. Do not add package-root exports and do not touch `src/continuous_refactoring/__init__.py` in this phase.
4. Update `loop.py` to import and use the moved helpers via full-path imports.
5. Preserve behavior exactly:
   - `revert_to(repo_root, revision)` still happens before restoring preserved files
   - preservation remains a no-op when the root is absent, outside the repo, or empty
   - restored files still land under their original relative paths
6. Keep `_run_refactor_attempt()` and `_retry_context()` in `loop.py` for now. This phase is only about preserved-workspace and reset primitives.
7. If the new module boundary needs error translation, do it only at the module boundary with `ContinuousRefactorError` and chained causes.

required_effort: medium
effort_reason: This is mostly controlled code motion, but it touches rollback-critical filesystem behavior and import boundaries.

## Precondition
- Phase 1 is complete and its focused regression coverage is green.
- `loop.py` still defines `_PreservedFile`, `_PreservedWorkspaceTree`, `_preserve_workspace_tree()`, and `_reset_to_source_baseline()`.
- No package-surface update is required yet; the new module remains internal-only in this phase.

## Definition of Done
- `src/continuous_refactoring/refactor_attempts.py` exists and owns `_PreservedFile`, `_PreservedWorkspaceTree`, `_preserve_workspace_tree()`, and `_reset_to_source_baseline()`.
- `loop.py` no longer defines those four helpers and imports them from `continuous_refactoring.refactor_attempts`.
- `loop.py` still owns `_run_refactor_attempt()` and `_retry_context()` after this phase.
- No package-root exports or `__init__.py` changes were introduced.
- Focused validation for this phase passes.
- The repository remains shippable at the phase checkpoint.

## Validation
- Run `uv run pytest tests/test_run.py -k "preserve or retry or validation or commit"`.
- Run `uv run pytest tests/test_loop_migration_tick.py`.
