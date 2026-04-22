# Phase 2: Extract Refactor Attempt

## Objective

Move ordinary retryable refactor-attempt execution into `src/continuous_refactoring/refactor_attempt.py` with the smallest behavior-preserving cut.

`loop.py` should still orchestrate retries. The new module should execute one attempt and return a `DecisionRecord`.

## Precondition

Phase 1 is complete: `AGENTS.md` names this live `loop.py` migration and clarifies that `_SUBMODULES` controls root re-exporting, focused tests characterize current retryable attempt behavior, including rollback, retry-start cleanup, artifact paths, validation failure, validation infrastructure failure, agent-requested transitions, successful commits, and agent-created commit squashing. Those tests pass with `_run_refactor_attempt()` still implemented in `loop.py`.

## Scope

Allowed production files:

- `src/continuous_refactoring/refactor_attempt.py`
- `src/continuous_refactoring/loop.py`

Allowed test files:

- `tests/test_run.py`
- `tests/test_e2e.py`
- `tests/test_run_once.py` only to preserve one-shot behavior if imports are adjusted
- `tests/test_continuous_refactoring.py` only to lock package-root export behavior

Do not move `_finalize_commit()` in this phase. Do not split `run_once()`.

## Instructions

1. Create `src/continuous_refactoring/refactor_attempt.py`.
   - Include `from __future__ import annotations`.
   - Use full-path imports only.
   - Define an explicit `__all__`, likely `("retry_context", "run_refactor_attempt")`.
2. Move `_run_refactor_attempt()` to `run_refactor_attempt()`.
   - Preserve keyword-only parameters at first.
   - Add a `finalize_commit` callable parameter instead of importing `_finalize_commit()` from `loop.py`.
   - Keep the call role strings `refactor` and `validation` unchanged.
3. Move `_retry_context()` to `retry_context()`.
   - Preserve output text exactly unless Phase 1 tests prove a better user-visible wording is needed.
4. Update `loop.py`.
   - Import `run_refactor_attempt` and `retry_context` from `continuous_refactoring.refactor_attempt`.
   - Replace `_run_refactor_attempt(...)` and `_retry_context(...)` call sites.
   - Keep `_finalize_commit()` in `loop.py`.
   - Remove imports from `loop.py` that are no longer needed for `run_loop()`, but keep imports still needed by `run_once()`.
5. Do not add `refactor_attempt` to `src/continuous_refactoring/__init__.py` `_SUBMODULES`.
   - Direct module imports like `continuous_refactoring.refactor_attempt` are enough.
   - `refactor_attempt.__all__` documents the new module surface only; it must not become root re-export input in this migration.
   - Avoid making `run_refactor_attempt` or `retry_context` part of the package-root public API as accidental churn.
6. Retarget only the tests that must change for the gate to stay green.
   - Ordinary `run_loop()` attempt tests that patch attempt internals should patch `continuous_refactoring.refactor_attempt.maybe_run_agent` or `continuous_refactoring.refactor_attempt.run_tests`.
   - `run_once()` tests should continue to patch `continuous_refactoring.loop.maybe_run_agent` and `continuous_refactoring.loop.run_tests`.
7. Preserve exception wrapping and causes already produced at module boundaries. Do not add extra translations inside the new module unless a boundary call currently needs one.
8. Add or adjust a package import test if coverage is missing.
   - `import continuous_refactoring.refactor_attempt` succeeds.
   - `continuous_refactoring.run_loop` remains available.
   - `continuous_refactoring.run_refactor_attempt` is absent unless the executor can justify a deliberate public API change, which should usually stop this phase for review.

## Definition of Done

- `refactor_attempt.py` owns one-attempt execution and retry-context formatting.
- `loop.py` no longer contains `_run_refactor_attempt()` or `_retry_context()`.
- `refactor_attempt.py` has module-local `__all__`, but `refactor_attempt` is not listed in `__init__._SUBMODULES`.
- `run_loop()` behavior, artifact layout, retry numbering, summaries, and commit ownership match Phase 1 characterization tests.
- `run_once()` behavior and monkeypatch paths remain stable.
- The package root API is not widened: `run_refactor_attempt` and `retry_context` are not root exports.
- The repository is shippable after this phase.

## Validation

Run:

```sh
uv run pytest tests/test_run.py tests/test_e2e.py tests/test_run_once.py
```

Run package import/export coverage if a test exists or was added:

```sh
uv run pytest tests/test_continuous_refactoring.py
```
