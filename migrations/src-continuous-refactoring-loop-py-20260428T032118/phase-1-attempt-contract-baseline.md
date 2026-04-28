# Phase 1: Attempt Contract Baseline

## Objective
Lock the retry and rollback contract in tests before moving code, with emphasis on preserved workspace restoration, decision persistence, validation failure recovery, and driver-owned commit behavior.

## Scope
- `tests/test_run.py`
- `tests/test_run_once.py`
- `tests/test_run_once_regression.py`
- `tests/test_loop_migration_tick.py` only if preserved migration workspace assertions belong there
- `src/continuous_refactoring/loop.py` only for tiny testability-neutral fixes required to expose already-existing behavior

## Instructions
1. Audit existing attempt-path coverage around agent non-zero exit, validation failure after edits, retry-context shaping, agent-created commits being undone, and preserved live-migration workspace restoration across retries.
2. Add missing regression coverage using example-based tests because this seam is integration-heavy and outcome-driven. Assert repository state, decision records, retry context, artifacts, and preserved migration state rather than collaborator call counts.
3. Cover both looping and one-shot flows where the contract already exists. Do not invent new behavior to make testing easier.
4. Keep `loop.py` changes minimal and behavior-preserving. No extraction yet.
5. If an extraction risk remains unverified after the added tests, record it precisely in the phase artifacts or a narrow `TODO`; do not hand-wave it in the phase doc.

required_effort: medium
effort_reason: The seam mixes retries, rollback, git history, and preserved migration state, so locking the behavior contract needs careful integration-style coverage.

## Precondition
- The migration still targets `src/continuous_refactoring/loop.py`.
- `loop.py` still contains `_run_refactor_attempt()`, `_preserve_workspace_tree()`, and `_reset_to_source_baseline()`.
- No `src/continuous_refactoring/refactor_attempts.py` module exists yet.

## Definition of Done
- `tests/test_run.py` explicitly covers all of these current behaviors: agent non-zero exit restores the baseline, validation failure restores the baseline, agent-requested `retry`/`abandon`/`blocked` produce the existing decision semantics, and preserved live-migration workspace files survive a source retry.
- `tests/test_run_once.py` or `tests/test_run_once_regression.py` explicitly covers the current driver-owned commit behavior relevant to one-shot execution.
- Any `loop.py` edits in this phase are limited to behavior-neutral test support.
- Focused validation for this phase passes.
- The repository remains shippable at the phase checkpoint.

## Validation
- Run `uv run pytest tests/test_run.py -k "retry or validation or commit or preserve"`.
- Run `uv run pytest tests/test_run_once.py tests/test_run_once_regression.py`.
- If this phase changed migration-state assertions, run `uv run pytest tests/test_loop_migration_tick.py`.
