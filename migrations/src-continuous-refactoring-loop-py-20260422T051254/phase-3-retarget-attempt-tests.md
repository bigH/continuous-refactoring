# Phase 3: Retarget Attempt Tests

## Objective

Make tests name the new boundary honestly and reduce brittle `loop.py` monkeypatching left over from the extraction.

This phase is mostly test cleanup. Production edits should be small and only in service of clearer module boundaries.

## Precondition

Phase 2 is complete: `src/continuous_refactoring/refactor_attempt.py` exists, has module-local `__all__`, is not listed in `__init__._SUBMODULES`, `run_loop()` calls `run_refactor_attempt()`, `retry_context()` is imported from the new module, `_finalize_commit()` still lives in `loop.py`, `run_once()` remains unchanged in behavior, the package root API is not widened, and all Phase 2 validation commands pass.

## Scope

Allowed files:

- `tests/test_run.py`
- `tests/test_e2e.py`
- `tests/test_run_once.py`
- `tests/test_scope_loop_integration.py`
- `src/continuous_refactoring/refactor_attempt.py` only for small naming/signature cleanup exposed by tests
- `src/continuous_refactoring/loop.py` only for stale import cleanup
- `tests/test_continuous_refactoring.py` only if Phase 2 left import/export assertions in the wrong place

Do not add a compatibility shim in `loop.py` for old attempt monkeypatch paths.

## Instructions

1. Search for stale test patch paths:
   - `continuous_refactoring.loop.maybe_run_agent`
   - `continuous_refactoring.loop.run_tests`
   - `continuous_refactoring.loop._run_refactor_attempt`
   - `continuous_refactoring.loop._retry_context`
2. Classify each occurrence:
   - Keep `loop.*` patches for `run_once()` tests and driver setup behavior that still genuinely lives in `loop.py`.
   - Move ordinary `run_loop()` attempt patches to `continuous_refactoring.refactor_attempt.*`.
   - Move retry-context direct tests, if any, to `continuous_refactoring.refactor_attempt.retry_context`.
3. Prefer helper functions that encode behavior, not implementation.
   - A helper like `patch_refactor_attempt_agent(...)` is acceptable if it reduces repeated string paths.
   - Avoid helpers that hide whether a test exercises `run_once()` or retryable `run_loop()` attempts.
4. Add a direct narrow test for `retry_context()` if retry prompt assertions are currently only indirect and hard to diagnose.
5. Keep integration tests outcome-based:
   - assert git log, worktree status, artifacts, events, summaries, and failure snapshots
   - avoid asserting that specific internal helpers were called
6. Confirm that `tests/test_run_once.py` still proves `run_once()` uses its existing one-shot path and did not silently start using retryable attempt semantics.
7. Preserve the Phase 2 export decision. Do not make retargeting easier by re-exporting attempt internals from the package root or `loop.py`.

## Definition of Done

- Ordinary retryable `run_loop()` attempt tests patch `continuous_refactoring.refactor_attempt` for agent and validation collaborators.
- `run_once()` tests still patch `continuous_refactoring.loop` for one-shot collaborators.
- No test depends on private moved names in `loop.py`.
- Test helper names make the exercised boundary obvious.
- Package-root tests, if present, still prove `run_refactor_attempt` and `retry_context` are not root exports.
- No production behavior changes beyond small import/name cleanup.
- The repository is shippable after this phase.

## Validation

Run:

```sh
uv run pytest tests/test_run.py tests/test_e2e.py tests/test_run_once.py tests/test_scope_loop_integration.py
```
