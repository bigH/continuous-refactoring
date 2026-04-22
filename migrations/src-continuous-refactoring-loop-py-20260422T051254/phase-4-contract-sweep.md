# Phase 4: Contract Sweep

## Objective

Finish the extraction by cleaning stale contracts, imports, and guidance without widening the migration.

This is the phase that makes the new shape feel intentional instead of merely moved.

## Precondition

Phase 3 is complete: tests patch the new attempt module where appropriate, `run_once()` tests retain their `loop.py` boundary, no test depends on `_run_refactor_attempt()` or `_retry_context()` in `loop.py`, the package-root API remains unchanged, and all Phase 3 validation commands pass.

## Scope

Allowed files:

- `src/continuous_refactoring/loop.py`
- `src/continuous_refactoring/refactor_attempt.py`
- `src/continuous_refactoring/__init__.py`
- `tests/test_run.py`
- `tests/test_e2e.py`
- `tests/test_run_once.py`
- `tests/test_continuous_refactoring.py`
- `AGENTS.md`

Do not move commit finalization, migration routing, baseline validation, or `run_once()` in this phase.

Do not add `refactor_attempt` to `_SUBMODULES` unless the phase deliberately changes the package-root API and updates tests plus `AGENTS.md`. The expected outcome is still no root export for attempt internals.

## Instructions

1. Inspect `loop.py` for imports and comments made stale by the extraction.
   - Remove unused imports.
   - Keep comments only if they carry load-bearing behavior, such as the driver-owned commit invariant.
2. Inspect `refactor_attempt.py` for names that still reflect the old location.
   - Use `run_refactor_attempt()` for the module entry point.
   - Use private helpers only for real local complexity.
   - Do not introduce a context dataclass unless the parameter list has become a clear readability problem.
3. Verify package import behavior.
   - `import continuous_refactoring` must still succeed.
   - Root exports for `run_loop`, `run_once`, and `run_migrations_focused_loop` must remain.
   - `import continuous_refactoring.refactor_attempt` must succeed.
   - `run_refactor_attempt` and `retry_context` must not be package-root exports.
4. Check repo guidance.
   - Confirm `AGENTS.md` names this active `loop.py` migration or no longer contains the stale "no active migration" statement.
   - Confirm `AGENTS.md` describes `_SUBMODULES` as the root re-export list and duplicate-symbol check input.
   - Add only tight, load-bearing guidance discovered during the extraction.
5. Search for stale references:
   - `_run_refactor_attempt`
   - `_retry_context`
   - `continuous_refactoring.loop.maybe_run_agent` in ordinary `run_loop()` attempt tests
   - `continuous_refactoring.loop.run_tests` in ordinary `run_loop()` attempt tests
6. Do not start the runner-up `transaction-boundary` work. If commit/rollback code now wants a home, leave a concise follow-up note in the phase result rather than moving it.

## Definition of Done

- `loop.py` is smaller and no longer owns retryable attempt internals.
- `refactor_attempt.py` has a clear domain boundary and no speculative abstractions.
- Package root imports and exported symbols remain compatible; attempt internals are direct-module imports only.
- Repo guidance does not contradict the presence or shape of this `loop.py` migration.
- No stale moved private names remain in production or tests.
- The full pytest gate passes.
- The repository is shippable after this phase.

## Validation

Run:

```sh
uv run pytest tests/test_run.py tests/test_e2e.py tests/test_run_once.py tests/test_scope_loop_integration.py
uv run pytest tests/test_continuous_refactoring.py
uv run pytest
```
