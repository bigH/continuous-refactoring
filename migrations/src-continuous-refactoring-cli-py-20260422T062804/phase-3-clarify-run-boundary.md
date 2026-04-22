# Phase 3: Clarify Run Boundary

## Objective

Make the remaining run command boundary in `cli.py` explicit and easy to audit while leaving `loop.py` behavior untouched.

The desired result is small: command handlers should clearly show which CLI guards run before `run_once()`, `run_loop()`, or `run_migrations_focused_loop()` execute, and where loop errors become CLI exits.

## Precondition

Phase 2 is complete. Review handling has moved to `review_cli.py`. `cli.py` still owns `_validate_targeting`, `_handle_run_once`, `_handle_run`, and `_run_with_loop_errors`, and the focused review tests pass against the new module.

## Scope

Allowed production files:

- `src/continuous_refactoring/cli.py`

Allowed test files:

- `tests/test_focus_on_live_migrations.py`
- `tests/test_run.py`

Optional only if command dispatch or stale warning behavior is accidentally exposed by the cleanup:

- `tests/test_cli_taste_warning.py`
- `tests/test_main_entrypoint.py`

Do not edit `loop.py` in this phase. Do not edit targeting modules.

## Instructions

1. Keep run/run-once handling in `cli.py`.
2. Group the run boundary helpers together:
   - targeting/scope guard;
   - loop error translation;
   - `run-once` handler;
   - `run` handler.
3. Rename private helpers only if the new names make the command boundary more truthful. If a helper is renamed, update tests in the same phase and do not leave private alias shims.
4. Preserve guard ordering:
   - `run-once` validates targeting before calling `run_once()`;
   - focused `run` calls `run_migrations_focused_loop()` without targeting or max-refactors checks;
   - ordinary `run` validates targeting before checking `--max-refactors`;
   - ordinary `run` requires `--max-refactors` when `--targets` is absent.
5. Preserve loop error translation:
   - `ContinuousRefactorError` prints the error to stderr;
   - the CLI exits with code 1;
   - the original exception remains the cause.
6. Do not move actual target resolution, retry handling, validation, commit handling, sleep handling, or migration execution out of `loop.py`.
7. Keep tests focused on user-visible guards and dispatch outcomes. It is acceptable to monkeypatch `continuous_refactoring.cli.run_loop` or `run_migrations_focused_loop` at this boundary.

## Definition of Done

- The run boundary helpers in `cli.py` are grouped and named clearly enough that guard order is obvious.
- `run-once`, ordinary `run`, and focused live-migration `run` behavior is unchanged.
- `ContinuousRefactorError` still translates to stderr plus `SystemExit(1)` at the CLI boundary.
- No loop execution, targeting resolution, retry, validation, commit, or artifact behavior moved out of `loop.py`.
- Tests cover the focused-run bypass and ordinary-run guard behavior after any helper retargeting.
- The repository is shippable after this phase.

## Validation

Run:

```sh
uv run pytest tests/test_focus_on_live_migrations.py tests/test_run.py tests/test_cli_review.py
```

If command dispatch or stale taste warning behavior is touched, also run:

```sh
uv run pytest tests/test_cli_taste_warning.py tests/test_main_entrypoint.py
```
