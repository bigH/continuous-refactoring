# Phase 4: Delete Routing Shim

## Objective

Remove the temporary migration tick compatibility path from `routing_pipeline.py` and verify the final contract.

After this phase, migration tick FQNs should be truthful: callers use `continuous_refactoring.migration_tick`.

## Precondition

Phase 3 is complete: production call sites and tests import or monkeypatch migration tick behavior through `continuous_refactoring.migration_tick`, `loop.py` has only minimal call-site edits, any stale `AGENTS.md` `loop.py` guidance has been resolved, and all Phase 3 validation commands pass.

## Scope

Allowed files:

- `src/continuous_refactoring/routing_pipeline.py`
- `src/continuous_refactoring/migration_tick.py`
- `src/continuous_refactoring/__init__.py`
- `tests/test_loop_migration_tick.py`
- `tests/test_focus_on_live_migrations.py`
- `tests/test_scope_loop_integration.py`
- `tests/test_continuous_refactoring.py`
- `AGENTS.md`

Touch `AGENTS.md` only if the new module layout contradicts its source layout guidance.

## Instructions

1. Remove `try_migration_tick` and `enumerate_eligible_manifests` from `routing_pipeline.__all__`.
2. Delete any routing-level aliases or delegation functions for migration tick behavior.
3. Ensure `routing_pipeline.py` imports only what it needs from `migration_tick.py`, ideally just `try_migration_tick()`.
4. Confirm all direct call sites use the final owner module. The no-match checks must pass when `rg` finds nothing; use shell guards rather than raw `rg` commands.
5. Confirm `migration_tick.__all__` exports the intended public tick boundary and no private helpers.
6. Update or add package/import tests only if needed to lock the no-duplicate-export contract.
7. Run the full test gate and fix any drift without widening the migration scope.

## Definition of Done

- `continuous_refactoring.migration_tick.try_migration_tick` and `continuous_refactoring.migration_tick.enumerate_eligible_manifests` are the only public FQNs for tick behavior.
- `routing_pipeline.py` no longer exports, aliases, or delegates migration tick symbols.
- No production or test monkeypatch target points through `routing_pipeline` for migration ticks.
- `routing_pipeline.py` is smaller and focused on routing, scope expansion, classification, and planning.
- The full test suite passes.
- The repository is shippable after this phase.

## Validation

Run:

```sh
if rg "routing_pipeline\\.(try_migration_tick|enumerate_eligible_manifests)" src tests; then
  echo "stale routing_pipeline migration tick reference found" >&2
  exit 1
fi

if rg "continuous_refactoring\\.routing_pipeline\\.(try_migration_tick|enumerate_eligible_manifests)" tests; then
  echo "stale routing_pipeline migration tick monkeypatch found" >&2
  exit 1
fi

uv run pytest tests/test_loop_migration_tick.py
uv run pytest tests/test_focus_on_live_migrations.py tests/test_scope_loop_integration.py
uv run pytest tests/test_continuous_refactoring.py
uv run pytest
```
