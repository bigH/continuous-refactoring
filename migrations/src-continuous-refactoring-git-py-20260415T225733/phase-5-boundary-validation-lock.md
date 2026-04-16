# Phase 5: boundary-validation-lock

## Objective

Lock all translated boundaries with deterministic tests covering cause retention and orchestration state continuity.

## Scope

- `tests/test_git_branching.py`
- `tests/test_config.py`
- `tests/test_targeting.py`
- `tests/test_phases.py`
- `tests/test_loop_migration_tick.py`
- `tests/test_run_once.py`
- `tests/test_run.py`

Out of scope:
- New production behavior outside error translation and orchestration outcomes.

## Deliverables

1. Add cause-chain tests for each migrated boundary layer:
   1. `git.py`: subprocess invocation failure wraps with `ContinuousRefactorError` and non-`None` `__cause__`.
   2. `config.py`: manifest read/parse and manifest write/replace failures wrap with non-`None` `__cause__`.
   3. `targeting.py`: `subprocess.run` invocation failure in `list_tracked_files` wraps with non-`None` `__cause__`.
2. Add/adjust orchestration outcome tests to ensure no status transitions changed by cause handling.
3. Keep status/output assertions stable for `run_once`/`run_loop`/`loop` and `phases`.

## Ready_when (machine-checkable)

1. Targeted commands all pass:
   - `uv run pytest tests/test_git_branching.py::test_run_observed_command_timeout`
   - `uv run pytest tests/test_git_branching.py::test_run_command_preserves_cause_on_subprocess_invocation_error`
   - `uv run pytest tests/test_config.py::test_load_manifest_invalid_json_preserves_cause`
   - `uv run pytest tests/test_config.py::test_save_manifest_replace_failure_preserves_cause`
   - `uv run pytest tests/test_targeting.py::test_list_tracked_files_subprocess_failure_preserves_cause`
   - `uv run pytest tests/test_phases.py::test_execute_phase_test_failure_reverts_workspace`
   - `uv run pytest tests/test_loop_migration_tick.py::test_eligible_ready_migration_advances_phase`
   - `uv run pytest tests/test_run.py::test_run_stops_after_max_consecutive_failures`
   - `uv run pytest tests/test_run_once.py::test_run_once_validation_gate`
   - `uv run pytest tests/test_run_once.py::test_run_once_prints_and_records_commit`
2. No production files outside scope listed in `Migration scope` are modified.
3. `git diff --name-only` includes only listed test files and migration docs after this phase.

## Deterministic assertions per layer

- Git layer pass criterion: test expects `err.__cause__` is `OSError`-family or `subprocess.SubprocessError`-family for a forced invocation failure.
- Config load layer pass criterion: JSON parse error or I/O read error in `load_manifest` produces `ContinuousRefactorError` with non-`None` cause.
- Config save layer pass criterion: atomic replace/write failure in `save_manifest` produces `ContinuousRefactorError` with non-`None` cause.
- Targeting layer pass criterion: `list_tracked_files` invocation error produces `ContinuousRefactorError` with non-`None` cause.
- Orchestration pass criterion: status strings and final outputs (`completed`, `baseline_failed`, `max_consecutive_failures`, `validation_failed`, `migration_failed`, `agent_failed`, `interrupted`, `failed`) remain unchanged for existing test scenarios.

## Validation

1. Run full phase test set in section above.
2. Confirm no behavior regression tests outside this cluster are introduced as required by scope.
3. Confirm migration docs remain final and self-consistent with plan/phases.
