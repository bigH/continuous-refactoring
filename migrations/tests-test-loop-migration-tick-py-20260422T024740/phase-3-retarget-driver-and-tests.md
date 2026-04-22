# Phase 3: Retarget Driver And Tests

## Objective

Point remaining production call sites and tests at `continuous_refactoring.migration_tick` directly.

This phase pays down the compatibility introduced in Phase 2, but leaves deletion of the routing shim to Phase 4.

## Precondition

Phase 2 is complete: `migration_tick.py` contains the real tick implementation, `routing_pipeline.route_and_run()` uses it, focused tests patch tick collaborators through `continuous_refactoring.migration_tick`, package import succeeds, the temporary routing compatibility path still exists for remaining callers, and all Phase 2 validation commands pass.

## Scope

Allowed files:

- `src/continuous_refactoring/loop.py`
- `src/continuous_refactoring/routing_pipeline.py`
- `tests/test_loop_migration_tick.py`
- `tests/test_focus_on_live_migrations.py`
- `tests/test_scope_loop_integration.py`
- `AGENTS.md`

`AGENTS.md` may be touched only to resolve stale guidance before editing `loop.py`.

## Instructions

1. Before editing `loop.py`, inspect the active `loop.py` migration note in `AGENTS.md`.
   - If the referenced migration directory exists and is current, read its plan/current phase before proceeding.
   - If the referenced migration directory is absent or stale, update `AGENTS.md` in this phase to remove or correct the stale active-migration note.
2. Update `loop.py` imports and call sites so the focused migrations loop uses:
   - `migration_tick.enumerate_eligible_manifests()`;
   - `migration_tick.try_migration_tick()`.
3. Keep `loop.py` edits minimal. Do not rename driver helpers, alter run-loop control flow, or clean up unrelated code.
4. Update any remaining tests that still monkeypatch migration tick behavior through `routing_pipeline` to patch the real owner module instead:
   - `continuous_refactoring.migration_tick.try_migration_tick`;
   - `continuous_refactoring.migration_tick.enumerate_eligible_manifests`;
   - `continuous_refactoring.migration_tick.check_phase_ready`;
   - `continuous_refactoring.migration_tick.execute_phase`.
5. Keep classifier, agent, scope expansion, and validation monkeypatches at their existing owner modules.
6. Add or keep a focused assertion that `routing_pipeline.route_and_run()` still falls through to classification when `migration_tick.try_migration_tick()` returns `("not-routed", record)`.
7. Do not delete routing compatibility attributes yet. Phase 4 owns deletion after this phase proves all intended callers have moved.

## Definition of Done

- `loop.py` no longer calls migration tick symbols through `routing_pipeline`.
- Tests no longer monkeypatch migration tick behavior through `routing_pipeline`.
- Any stale `loop.py` active-migration guidance in `AGENTS.md` is resolved before the `loop.py` edit.
- Driver behavior is unchanged: focused loop exits on no eligible manifests, stops on blocked/abandon thresholds, and terminates cleanly when all eligible migrations defer.
- The repository is shippable after this phase.

## Validation

Run:

```sh
uv run pytest tests/test_loop_migration_tick.py
uv run pytest tests/test_focus_on_live_migrations.py tests/test_scope_loop_integration.py
uv run pytest tests/test_run.py::test_run_phase_ready_check_failure_logs_phase_ready_role tests/test_run.py::test_run_phase_execute_validation_failure_logs_phase_validation_role
```
