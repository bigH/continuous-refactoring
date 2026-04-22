# Phase 2: Extract Migration Tick

## Objective

Move the migration tick implementation into `src/continuous_refactoring/migration_tick.py` and retarget focused tick tests to the new owner module.

This phase may keep a temporary delegation from `routing_pipeline.py` for existing production callers. It must not pretend old `routing_pipeline.check_phase_ready` or `routing_pipeline.execute_phase` monkeypatches still affect the moved body.

## Precondition

Phase 1 is complete: focused tests characterize current migration tick behavior at the `routing_pipeline` boundary, no production files were changed in Phase 1, `try_migration_tick()` and `enumerate_eligible_manifests()` still live in `routing_pipeline.py`, no `migration_tick.py` module exists, and all Phase 1 validation commands pass.

## Scope

Allowed files:

- `src/continuous_refactoring/migration_tick.py`
- `src/continuous_refactoring/routing_pipeline.py`
- `src/continuous_refactoring/__init__.py`
- `tests/test_loop_migration_tick.py`
- `tests/test_continuous_refactoring.py`

Do not edit `loop.py` in this phase.

## Instructions

1. Create `src/continuous_refactoring/migration_tick.py`.
2. Move the migration tick domain code from `routing_pipeline.py`:
   - `enumerate_eligible_manifests()`;
   - `try_migration_tick()`;
   - the finalize-commit protocol type or an equivalent private protocol;
   - private helpers for target labels, ready-check decisions, phase execution decisions, deferral, and human-review blocking where they improve readability.
3. Import `check_phase_ready` and `execute_phase` into `migration_tick.py` from `continuous_refactoring.phases`.
4. Update `routing_pipeline.route_and_run()` to call `migration_tick.try_migration_tick()`.
5. Leave only temporary routing-level delegations or aliases for `try_migration_tick()` and `enumerate_eligible_manifests()` if needed by callers not yet retargeted. Do not add broader re-export shims.
6. Retarget focused migration tick tests in `tests/test_loop_migration_tick.py` that patch tick collaborators:
   - `continuous_refactoring.migration_tick.check_phase_ready`;
   - `continuous_refactoring.migration_tick.execute_phase`;
   - `continuous_refactoring.migration_tick.try_migration_tick` when testing routing fallback behavior;
   - `continuous_refactoring.migration_tick.enumerate_eligible_manifests` when testing focused loop enumeration behavior.
7. Keep classifier, scope expansion, agent, and validation monkeypatches at their existing owner modules.
8. Add `migration_tick` to package import coverage so `src/continuous_refactoring/__init__.py` exercises duplicate export detection.
9. Ensure any symbol exported by `migration_tick.__all__` does not collide with another module export. If routing compatibility attributes remain, keep them out of `routing_pipeline.__all__` and document that Phase 4 deletes them.

## Definition of Done

- `migration_tick.py` owns the real implementations of `try_migration_tick()` and `enumerate_eligible_manifests()`.
- `routing_pipeline.py` no longer contains the tick workflow body; it calls or delegates to `migration_tick` for migration ticks.
- `route_and_run()` behavior is unchanged.
- Focused tests that patch `check_phase_ready()` or `execute_phase()` patch `continuous_refactoring.migration_tick`, not `continuous_refactoring.routing_pipeline`.
- Any temporary routing compatibility is narrow, documented by the phase plan, and not relied on for collaborator monkeypatching.
- Package import succeeds without duplicate exported symbols.
- The repository is shippable after this phase.

## Validation

Run:

```sh
uv run pytest tests/test_loop_migration_tick.py
uv run pytest tests/test_focus_on_live_migrations.py tests/test_scope_loop_integration.py
uv run pytest tests/test_continuous_refactoring.py
```
