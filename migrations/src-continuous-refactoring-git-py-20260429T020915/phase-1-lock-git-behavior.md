# Phase 1: Lock Git Behavior

## Scope
- `tests/test_git.py`
- `src/continuous_refactoring/git.py`
- If package-root export coverage is the smallest stable place to pin symbol
  exposure:
  - `tests/test_continuous_refactoring.py`

required_effort: low
effort_reason: focused characterization work on a small module and its tests

## Precondition
This migration is at its first executable phase, and
`src/continuous_refactoring/git.py` still exposes the current public helpers
listed in its `__all__` for downstream callers and package-root re-export.

## Instructions
- Add or tighten characterization tests before restructuring `git.py`.
- Make the current contract explicit for the seams most likely to break during
  refactoring:
  - `run_command()` checked failure wrapping,
  - `run_command(check=False)` passthrough behavior,
  - nested causes for startup failures and non-zero exits,
  - `workspace_status_lines()` and `require_clean_worktree()`,
  - `discard_workspace_changes()` and `revert_to()`,
  - `git_commit()` and `undo_last_commit()`.
- Prefer real repositories through the existing test helpers over mocks unless
  the behavior under test is subprocess startup failure.
- Keep production edits minimal. Only touch `git.py` if a tiny source change is
  required to expose already-shipped behavior to tests.

## Definition of Done
- `tests/test_git.py` contains explicit coverage for:
  - `run_command()` checked failure wrapping and unchecked passthrough,
  - nested startup and non-zero-exit causes,
  - workspace status and clean-worktree enforcement,
  - destructive reset/clean behavior,
  - commit, undo, and revert behavior.
- Any package-root git exports this migration intends to preserve are pinned by
  the smallest explicit coverage needed.
- No caller-facing behavior has changed beyond test-only clarification.
- The configured broad validation command passes.

## Validation
- Run `uv run pytest tests/test_git.py`.
- If package-root export coverage is added or changed, run
  `uv run pytest tests/test_continuous_refactoring.py`.
- Finish with `uv run pytest`.
