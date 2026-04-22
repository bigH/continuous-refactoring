# Phase 2: Extract Execution Steps

## Objective

Make `execute_phase()` read as a compact orchestration pipeline while keeping `phases.py` as the owner of phase execution.

The function should show the phase transaction at a glance: prepare attempt, run agent, handle agent failure, run validation, retry or fail, complete manifest.

## Precondition

Phase 1 is complete: the focused tests cover the main success, failure, retry, rollback, artifact, and manifest-completion contracts, and all Phase 1 validation commands pass.

## Scope

Allowed files:

- `src/continuous_refactoring/phases.py`
- `tests/test_phases.py` only if helper extraction requires minor test-helper naming updates

Do not edit public call sites, package exports, prompt composition, migration manifest parsing, or artifact internals.

## Instructions

1. Preserve these public symbols and their module:
   - `ReadyVerdict`
   - `ExecutePhaseOutcome`
   - `check_phase_ready()`
   - `execute_phase()`
2. Introduce private value objects only where they carry repeated state cleanly. Good candidates:
   - Attempt paths and metadata for one execution retry.
   - Agent execution result containing `status`, `phase_reached`, `summary`, and `focus`.
   - Validation result that distinguishes success, retryable failure, and terminal failure without hiding rollback.
3. Extract private helpers around the existing steps:
   - Build attempt paths and compose prompt inputs.
   - Run the phase execution agent and read status.
   - Log and translate agent execution failures.
   - Run validation.
   - Decide retry versus terminal validation failure.
   - Mark the phase complete and persist the manifest.
4. Keep rollback ownership in `phases.py`.
   - Retry rollback before the next agent attempt must remain.
   - Terminal failure rollback must remain.
   - Do not move rollback into `git.py`, `artifacts.py`, or a generic transaction abstraction.
5. Keep helper names domain-specific. Prefer names like `_run_phase_agent`, `_run_phase_validation`, `_complete_phase`, and `_retry_phase_execution_context`.
6. Preserve artifact path layout and event fields exactly.
7. Preserve `status_summary()` behavior:
   - Agent nonzero and validation failures summarize from agent status with the existing fallback.
   - Sanitization remains boundary-oriented.
8. Do not add re-export shims or move symbols to another module.

## Definition of Done

- `execute_phase()` is a short orchestration function over named private helpers.
- Phase execution behavior is unchanged for success, agent failure, validation failure, validation infra failure, retry exhaustion, unlimited retries, and stale phase references.
- Artifact files and event roles remain stable: `phase.execute`, `phase.validation`, and the existing `phase-execute/` file names.
- Manifest completion still advances the cursor, marks the final phase as done, clears deferral fields, and persists atomically through `save_manifest()`.
- The repository is shippable after this phase.

## Validation

Run:

```sh
uv run pytest tests/test_phases.py
uv run pytest tests/test_loop_migration_tick.py tests/test_focus_on_live_migrations.py
uv run pytest tests/test_run.py::test_run_phase_execute_validation_failure_logs_phase_validation_role tests/test_run.py::test_run_phase_execute_validation_infra_failure_logs_phase_validation_role
```
