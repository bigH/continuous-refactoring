# In-Place Git Error Contract

## Strategy

Keep `src/continuous_refactoring/git.py` as the git module API and harden it in place.

- Keep exported names and callsites stable.
- Add a focused `GitCommandError(ContinuousRefactorError)` in `git.py` for failed checked runs.
- Update `run_command()` to always wrap subprocess failures with `from`-chained causes.
- Preserve the current semantics (`check` default remains True, callers can still suppress with `check=False`).
- Leave driver flow unchanged, but make the module boundary more truthful and diagnosable.

## Tradeoffs

Pros:
- Lowest migration shock: external callers and tests keep working unless they assert on exact string messages.
- Directly addresses taste point about translation at boundaries and preserving root causes.
- Minimal blast radius across `loop.py`, `phases.py`, `routing_pipeline.py`, and migration drivers.

Cons:
- No architectural cleanup of git command call patterns in other modules.
- Error payload improvements are additive, not a behavior model rewrite.
- `ContinuousRefactorError` message contracts remain broad, so downstream observability can still be improved later.

## Estimated Phases

1. Lock behavior with tests in `tests/test_git.py`.
- Add failure-path assertions for missing `git` binary and failed checked commands.
- Assert `__cause__` exists and that output remains attached.

2. Refactor command boundary in `src/continuous_refactoring/git.py`.
- Add `GitCommandError` and centralized `_run_command` internals.
- Convert ad hoc `ContinuousRefactorError` construction into nested-error wrapping.
- Keep existing helpers: `current_branch`, `get_head_sha`, `repo_change_count`, `discard_workspace_changes`, `undo_last_commit`, `revert_to`.

3. Run targeted then broad validation.
- `uv run pytest tests/test_git.py`
- `uv run pytest tests/test_no_driver_branching.py tests/test_scope_candidates.py tests/test_scope_loop_integration.py`
- `uv run pytest`

## Risk Profile

Low-to-medium. Biggest risk is accidental tightening of existing behavior in `run_command`.

Mitigations:
- Keep command text formatting behavior unchanged.
- Keep successful paths untouched.
- Only broaden exception information, not command semantics.

## Best Fit

Best when you want a truthful low-risk boundary refactor with fast delivery and no coordinated module churn.
