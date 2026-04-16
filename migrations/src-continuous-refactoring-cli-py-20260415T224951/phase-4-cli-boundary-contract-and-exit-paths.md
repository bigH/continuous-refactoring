# Phase 4: cli-boundary-contract-and-exit-paths

## Objective

Finalize boundary ownership at CLI entry/dispatch edges and verify deterministic, shippable exit behavior with intact causal chains.

## Scope

- `src/continuous_refactoring/cli.py`
- `src/continuous_refactoring/__init__.py`
- `src/continuous_refactoring/__main__.py`

No direct test file edits.

## Instructions

1. Consolidate user-facing failure translation in CLI boundaries only:
   - `_run_with_loop_errors`
   - command entrypoints that already own exit conversion (`cli_main`, `_dispatch_handler`).
2. Remove any duplicate local conversion where ownership already exists at upper boundary.
3. Keep command dispatch shape and parser options unchanged.
4. In CLI-owned wrappers:
   1. preserve causes with `raise ... from error` when converting caught module exceptions,
   2. keep existing exit-code values (`1` or `2`) tied to current contracts.
5. Keep `__main__.py` as pass-through entry and update `__init__.py` only for boundary-safe exports if required by the migration (avoid unrelated import-shape churn).

## Ready_when (mechanical)

1. In `cli.py`, `__init__.py`, and `__main__.py`, all boundary conversions of caught exceptions include `from`.
2. CLI top-level exit path remains single-wrapped:
   - no raw `SystemExit` thrown from modules below `cli`.
3. `git diff --name-only` contains only the scoped files for this phase.

## Validation

1. Run CLI validation commands in existing suites:
   1. `tests/test_cli_taste_warning.py`
   2. `tests/test_cli_init_taste.py`
   3. `tests/test_cli_review.py`
2. Verify at least one test covers each changed boundary path with:
   - expected exit code,
   - expected `stderr` shape,
   - non-`None` `exc.__cause__` for wrapped failures.
3. Confirm unchanged stable behavior for non-error flows through:
   - `run-once`,
   - `run`,
   - `review`.

