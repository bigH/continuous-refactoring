# In-Place Execution Pipeline

## Strategy

Keep `src/continuous_refactoring/phases.py` as the owner of phase readiness and phase execution, but make `execute_phase()` read as a small orchestration pipeline instead of a nested control-flow block.

Recommended shape:

1. Preserve the public API: `ReadyVerdict`, `ExecutePhaseOutcome`, `check_phase_ready()`, and `execute_phase()`.
2. Extract private helpers around the real steps:
   - build attempt paths and prompt inputs
   - run the execution agent and read its status
   - run validation
   - decide retry vs terminal failure
   - mark the phase complete and persist the manifest
3. Keep rollback ownership in `phases.py`; it is part of the phase execution boundary.
4. Add small value objects only where they carry repeated state cleanly, for example an execution attempt result with `status`, `phase_reached`, `summary`, and `focus`.
5. Strengthen `tests/test_phases.py` around failure surfaces before reshaping the function.

This is the best default. The module boundary is already meaningful: it translates agent/test/git/manifest interactions into a phase outcome for `routing_pipeline.py`.

## Tradeoffs

Pros:
- Lowest churn and no public import reshaping.
- Keeps monkeypatch targets stable in the broad migration tests.
- Makes the long function easier to audit without inventing a new subsystem.
- Fits the taste guidance: single-call helpers are acceptable when they document flow.
- Avoids `__init__.py` export churn and duplicate-symbol risk.

Cons:
- `phases.py` still owns both readiness and execution.
- Retry semantics remain coupled to agent status parsing and artifact logging.
- The module remains a boundary coordinator, not a pure domain module.

## Estimated Phases

1. **Safety net**
   - Add or tighten tests for agent exception failure, nonzero agent exit, validation infrastructure failure, unknown phase completion, manifest cleanup fields, and unlimited retry budget if under-covered.
   - Validation: `uv run pytest tests/test_phases.py tests/test_loop_migration_tick.py tests/test_focus_on_live_migrations.py`.

2. **Extract execution steps**
   - Split `execute_phase()` into private helpers while preserving behavior and artifact paths.
   - Keep helper names domain-specific: `run_phase_agent`, `run_phase_validation`, `complete_phase`, `fail_phase_execution`.
   - Do not move symbols or add re-export shims.

3. **Tidy and delete**
   - Remove duplicated failure branches exposed by the extraction.
   - Rename weak locals such as `current_retry` only if the new name clarifies retry budget behavior.
   - Run `uv run pytest`.

## Risk Profile

Low to medium risk. Most danger is accidental behavior drift in rollback counts, retry numbering, artifact paths, or manifest persistence.

Main watch-outs:
- The current tests assert exact rollback behavior in retry exhaustion; preserve or intentionally update that contract.
- `retry` starts as a caller-visible attempt number, while the loop increments internally. Rename carefully.
- `status_summary()` intentionally uses agent status as the summary source even when validation failed; do not replace it with raw test output.
- Artifact paths are user-visible debugging surfaces.

## Best Fit

Choose this when the migration goal is to make `phases.py` smaller and clearer without changing ownership boundaries. This should be the first migration unless a later phase explicitly wants to split readiness or manifest completion into separate modules.
