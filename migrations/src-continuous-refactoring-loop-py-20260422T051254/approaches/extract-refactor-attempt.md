# Extract Refactor Attempt

## Strategy

Move the retryable non-migration refactor attempt out of `loop.py` into a focused module, likely `src/continuous_refactoring/refactor_attempt.py`.

Move:
- `_run_refactor_attempt()`
- `_retry_context()`
- the small status/validation/rollback helpers that become obvious during the move

Keep the outer loops in `loop.py`. They still own target iteration, baseline checks, migration routing, consecutive-failure policy, sleeping, and artifact run lifecycle. The new module owns exactly one unit of work: run an agent for one target, validate, roll back or finalize, and return a `DecisionRecord`.

The commit finalizer can stay injected as a callable so migration execution and ordinary refactors continue sharing the existing "driver owns commits" rule without creating a speculative interface.

## Tradeoffs

Pros:
- Best first cut. It removes the densest 250-line block while preserving the current driver shape.
- Creates a truthful domain boundary: an attempt is not the same thing as a loop mode.
- Retry behavior becomes testable without walking the full `run_loop()` target machinery.
- Keeps `loop.py` public surface stable: `run_once`, `run_loop`, and `run_migrations_focused_loop` remain where callers expect them.

Cons:
- Existing tests monkeypatch `continuous_refactoring.loop.maybe_run_agent` and `continuous_refactoring.loop.run_tests`; they will need to patch the new module instead or use outcome-based helpers.
- `_run_refactor_attempt()` currently reaches many collaborators, so the first extraction may still have a wide parameter list.
- Does not address duplication between `run_loop()` and `run_migrations_focused_loop()`.

## Estimated Phases

1. **Characterize attempt behavior**
   - Add or tighten narrow tests for agent nonzero, validation failure, agent-requested retry/abandon/blocked, successful commit, and agent-created commits being squashed.
   - Prefer outcome assertions: git log, workspace status, persisted `DecisionRecord`, artifact paths.
   - Validation: `uv run pytest tests/test_run.py tests/test_run_once.py`.

2. **Extract attempt module**
   - Create `refactor_attempt.py` with `run_refactor_attempt()` and `retry_context()`.
   - Use full-path imports and explicit `__all__`.
   - Update `loop.py` imports and call sites.
   - Update `src/continuous_refactoring/__init__.py` if the new symbols should be public; otherwise include the module in `_SUBMODULES` only if exported symbols are intended. Avoid re-exporting private plumbing by default.

3. **Retarget tests**
   - Move monkeypatch paths from `continuous_refactoring.loop.*` to `continuous_refactoring.refactor_attempt.*` where they patch attempt internals.
   - Keep end-to-end loop tests patching `loop` only when they are truly testing driver behavior.

4. **Tidy the seam**
   - Rename extracted helpers to public-within-module names if they are not private implementation details.
   - Remove any comments made obsolete by clearer function boundaries.
   - Run `uv run pytest`.

## Risk Profile

Medium-low. Behavior should be mechanical to preserve, and the rollback/commit rules are already well covered.

Main watch-outs:
- Do not accidentally skip `discard_workspace_changes()` at the start of each retry.
- Preserve exception causes when wrapping external agent or validation failures.
- Keep artifact filenames stable: `agent.stdout.log`, `agent.stderr.log`, `tests.stdout.log`, `tests.stderr.log`, and Codex `agent-last-message.md`.
- Keep the driver-owned commit invariant: if the agent commits, reset soft to `head_before`, then create one driver commit.

## Best Fit

Choose this as the recommended first migration. It cuts real complexity with the least public churn and leaves better options open for a later phase.
