# Phase 3: Tighten Error Boundaries

## Scope
- `src/continuous_refactoring/git.py`
- `tests/test_git.py`
- If direct callers need targeted confirmation:
  - `tests/test_targeting.py`
  - `tests/test_refactor_attempts.py`

required_effort: low
effort_reason: localized boundary cleanup with narrow downstream verification

## Precondition
Phase 2 is marked complete, and `run_command()` is still the subprocess entry
point used by the public git helpers touched by this migration.

## Instructions
- Keep subprocess failure translation at `run_command()` by default.
- Preserve nested causes from both command startup failures and non-zero exits.
- Let higher-level helpers bubble `GitCommandError` unchanged unless they add
  domain-owned context that is already part of that helper's contract, such as
  detached-HEAD reporting in `current_branch()` or the user-facing clean
  worktree message in `require_clean_worktree()`.
- Remove redundant re-wrapping or helper layering that obscures the original
  failure source.
- Extend focused tests only where needed to make the intended error-boundary
  contract explicit.

## Definition of Done
- `run_command()` remains the only general subprocess failure-translation
  boundary in `git.py`.
- Higher-level helpers add context only for their own domain contract and do
  not add duplicate wrapper layers around `GitCommandError`.
- Focused regression tests would catch loss of nested causes, changed command
  failure payloads, or new redundant wrapping.
- Downstream suites that directly consume `GitCommandError` still pass without
  API churn.
- The configured broad validation command passes.

## Validation
- Run `uv run pytest tests/test_git.py`.
- If direct caller expectations around `GitCommandError` are touched, run
  `uv run pytest tests/test_targeting.py tests/test_refactor_attempts.py`.
- Finish with `uv run pytest`.
