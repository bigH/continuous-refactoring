# Phase 3 — Boundary normalization for top-level command helpers

## Scope (hard allowed set)

- `src/continuous_refactoring/agent.py` (only)
  - `maybe_run_agent`
  - `run_tests`
  - `summarize_output` (documentation-level edits only if needed for output contract clarity)
  - any small local helper used only by these functions
- `src/continuous_refactoring/__init__.py` (only if export wiring requires explicit refresh)
- `tests/test_continuous_refactoring.py` (add/update)
- `tests/test_loop_migration_tick.py` (add/update)
- `tests/test_phases.py` (add/update)
- `tests/test_run.py` (add/update)
- `tests/test_run_once.py` (add/update)

No other source file may be edited in phase 3.

## Goal

Make boundary-level command translation consistent between `run_observed_command` callers
while preserving the existing success contract for loop/phase flows.

## Ready when (machine-checkable)

- Exact acceptance checks pass:
  1. `uv run pytest tests/test_continuous_refactoring.py::test_build_command_rejects_unknown_agent`
  2. `uv run pytest tests/test_continuous_refactoring.py::test_compose_full_prompt_orders_previous_failure_then_fix_amendment`
  3. New phase-3 test `uv run pytest tests/test_continuous_refactoring.py::test_run_tests_rejects_bad_command_string_with_cause`
  4. New phase-3 test `uv run pytest tests/test_continuous_refactoring.py::test_maybe_run_agent_preserves_cause_from_build_or_observed_command`
  5. `uv run pytest tests/test_run_once.py::test_run_once_validation_gate`
  6. `uv run pytest tests/test_run.py::test_run_once_validation_gate`
- For `run_tests`:
  - malformed command string (`run_tests(" [", repo_root, ...)`) raises `ContinuousRefactorError` and `exc.value.__cause__ is not None`.
  - valid command string still returns `CommandCapture` with `returncode == 0`.
- For `maybe_run_agent`:
  - valid command path (`agent="codex", last_message_path=tmp_path`) still returns successful `CommandCapture` from `run_observed_command`.
  - unsupported command still raises `ContinuousRefactorError` with boundary-meaningful message and no swallowing of runtime cause from `build_command` if it is already boundary-level.

## Detailed instructions

1. In `maybe_run_agent`:
   - keep pre-check `_require_agent_on_path(agent)` as current boundary.
   - do not swallow actionable `ContinuousRefactorError` from `build_command`.
   - when `build_command` raises, preserve the exception (only wrap if needed for boundary message and always `from`-chain).
2. In `run_tests`:
   - parse command with `shlex.split` as boundary and wrap parse errors with
     `ContinuousRefactorError(... ) from error`.
   - keep launch/deadline semantics delegated to `run_observed_command`.
3. Keep `summarize_output` behavior unchanged for existing call sites unless message slicing becomes incorrect in tests.
4. Verify `src/continuous_refactoring/__init__.py` still exports the same module symbols; avoid accidental export churn.

## Validation

- New/updated tests should assert concrete outcomes only:
  - `__cause__` is set when expected,
  - command parsing errors are wrapped at the boundary,
  - success values (`returncode`, output fields) are unchanged for valid commands.
