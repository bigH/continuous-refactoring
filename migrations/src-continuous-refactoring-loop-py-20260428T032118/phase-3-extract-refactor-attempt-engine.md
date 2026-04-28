# Phase 3: Extract Refactor Attempt Engine

## Objective
Move the retryable source-refactor attempt engine into `refactor_attempts.py`, leaving `loop.py` to orchestrate target selection, action budgeting, migration probing, and top-level retry flow.

## Scope
- `src/continuous_refactoring/refactor_attempts.py`
- `src/continuous_refactoring/loop.py`
- `tests/test_run.py`
- `tests/test_run_once.py`
- `tests/test_run_once_regression.py`
- `tests/test_loop_migration_tick.py` only if shared preserved-state coverage or imports require adjustment

## Instructions
1. Move `_run_refactor_attempt()` into `refactor_attempts.py`.
2. Move `_retry_context()` into `refactor_attempts.py` in the same phase. It is only used by the retryable source-refactor loop, so do not leave it behind in `loop.py`.
3. Keep the extracted API outcome-oriented: `loop.py` should ask the module to run one retryable refactor attempt and receive a `DecisionRecord`, not rebuild the old control flow through callbacks.
4. Preserve these contracts exactly:
   - workspace cleanup before each attempt
   - preserved migration files restored before the agent runs and after rollback paths
   - agent non-zero exit becomes the existing retry decision record
   - validation failure restores baseline and records retry context
   - agent `retry` / `abandon` / `blocked` statuses keep the same decision-record semantics
   - final commit still goes through the driver-owned commit path
5. Simplify the `run_loop()` retry slab around the extracted engine, but keep orchestration visible in `loop.py`. Do not replace one knot with a pile of tiny wrappers.
6. Do not force `run_once()` onto this engine. Update it only if shared imports or helper ownership require small compatibility edits.

required_effort: high
effort_reason: This is the behavior-critical move where retry semantics, artifact logging, rollback, and commit ownership can silently drift.

## Precondition
- Phase 2 is complete and `refactor_attempts.py` already owns the preserved-workspace/reset primitives.
- Phase 1 regression coverage is still green and treated as the behavior contract.
- `loop.py` still owns the active `_run_refactor_attempt()` implementation at the start of this phase.

## Definition of Done
- `refactor_attempts.py` owns `_run_refactor_attempt()` and `_retry_context()`.
- `loop.py` no longer defines `_run_refactor_attempt()` or `_retry_context()`.
- `run_loop()` still contains the retry loop and top-level orchestration, but delegates single-attempt execution to `refactor_attempts.py`.
- Phase 1 contract tests continue to pass without expectation changes that weaken the locked behavior.
- `run_once()` remains separate from the new engine except for minimal compatibility edits.
- Focused validation for this phase passes.
- The repository remains shippable at the phase checkpoint.

## Validation
- Run `uv run pytest tests/test_run.py`.
- Run `uv run pytest tests/test_run_once.py tests/test_run_once_regression.py tests/test_loop_migration_tick.py`.
