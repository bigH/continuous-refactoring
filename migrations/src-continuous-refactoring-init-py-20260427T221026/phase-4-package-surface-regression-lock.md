# Phase 4: Lock package-surface regression criteria

## Objective
Complete the migration by hardening the package-surface assertions so regression against public/export behavior is explicit and repeatable.

## Scope
- `tests/test_continuous_refactoring.py`

## Instructions
1. Finalize export assertions for:
   - `continuous_refactoring.__all__` shape and ordering
   - expected public names still present
   - `migration_manifest_codec` internals not exported from package root
2. Ensure assertions are tolerant of unrelated future non-export additions outside this package surface.
3. Keep runtime behavior untouched in all other modules.
4. Confirm all previous phase-specific quality gates still pass with this tightened contract.

## Precondition
- `rg -n "duplicate|origin" src/continuous_refactoring/__init__.py` confirms duplicate diagnostics are present.
- `uv run pytest tests/test_continuous_refactoring.py`
- `uv run python -m continuous_refactoring --help`
- `test -z "$(git diff --name-only -- src/continuous_refactoring/loop.py src/continuous_refactoring/prompts.py src/continuous_refactoring/routing_pipeline.py src/continuous_refactoring/migrations.py src/continuous_refactoring/planning.py src/continuous_refactoring/scope_expansion.py src/continuous_refactoring/agent.py)"`
- `uv run python - <<'PY'`
```python
import continuous_refactoring
import importlib

for module in (
    "continuous_refactoring.loop",
    "continuous_refactoring.prompts",
    "continuous_refactoring.routing_pipeline",
    "continuous_refactoring.migrations",
    "continuous_refactoring.planning",
    "continuous_refactoring.scope_expansion",
    "continuous_refactoring.agent",
):
    importlib.import_module(module)

assert isinstance(continuous_refactoring.__all__, tuple)
PY

## Definition of Done
- `tests/test_continuous_refactoring.py` contains explicit regression lock assertions for the package-surface contract.
- The migration lock does not require production changes outside this migration.
- Duplicate provenance diagnostics and helper behavior remain stable.
- Full-shipment checks pass after this phase.

## Validation steps
1. `uv run pytest tests/test_continuous_refactoring.py`
2. `uv run pytest`
3. `uv run python -m continuous_refactoring --help`
4. `uv run python - <<'PY'`
```python
import continuous_refactoring
import importlib

for module in (
    "continuous_refactoring.loop",
    "continuous_refactoring.prompts",
    "continuous_refactoring.routing_pipeline",
    "continuous_refactoring.migrations",
    "continuous_refactoring.planning",
    "continuous_refactoring.scope_expansion",
    "continuous_refactoring.agent",
):
    importlib.import_module(module)

assert isinstance(continuous_refactoring.__all__, tuple)
print("phase-4-shippability-ok", len(continuous_refactoring.__all__))
```
