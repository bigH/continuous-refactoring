# Phase 2: Reorganize Domain Flow

## Scope
- `src/continuous_refactoring/git.py`
- `tests/test_git.py`

required_effort: low
effort_reason: in-place helper reordering and local cleanup only

## Precondition
Phase 1 is marked complete, and `tests/test_git.py` already contains
characterization coverage for `run_command()`, workspace status helpers,
clean-worktree enforcement, destructive reset helpers, and commit/revert
flows.

## Instructions
- Reorganize `git.py` so it reads top-down in this order:
  1. subprocess execution and failure translation,
  2. read-only repository state queries,
  3. destructive worktree and history mutations.
- Preserve the existing public symbol set in `git.py.__all__` and the existing
  behavior of those helpers.
- Simplify private helper flow only as needed to support that ordering.
- If you introduce any private helper solely to stage the reorganization, name
  it plainly and treat it as transitional so Phase 4 can delete it explicitly.
- Do not change package imports, split the module, or change caller contracts.

## Definition of Done
- `src/continuous_refactoring/git.py` is ordered top-down by the three domains
  named above.
- The public symbol set exposed from `git.py.__all__` is unchanged.
- `discard_workspace_changes()` and `revert_to()` both delegate their reset and
  clean work through `_reset_hard_and_clean()` rather than duplicating inline
  command sequences.
- The characterization tests added in Phase 1 still pass without changing the
  contract they assert.
- The configured broad validation command passes.

## Validation
- Run `uv run pytest tests/test_git.py`.
- If the edit unexpectedly touches package-root export behavior, run
  `uv run pytest tests/test_continuous_refactoring.py`.
- Finish with `uv run pytest`.
