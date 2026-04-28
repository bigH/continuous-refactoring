# Phase 2: Introduce explicit package export collector

## Objective
Refactor `__init__.py` so exported symbols are collected through an explicit module list and helper, without changing runtime behavior.

## Scope
- `src/continuous_refactoring/__init__.py`
- `tests/test_continuous_refactoring.py` (to align assertions if needed)

## Instructions
1. Introduce an explicit, ordered module descriptor for package export source modules.
2. Add or replace a collector helper, for example `collect_package_exports(modules: tuple[type[object], ...]) -> tuple[str, ...]`.
3. Compute `__all__` via that helper and keep return type as `tuple[str, ...]`.
4. Keep `_SUBMODULES` available and unchanged in value shape.
5. Preserve eager import order and exported symbol order.
6. Preserve existing duplicate exception behavior shape for now; `RuntimeError` remains, with clearer messages added in phase 3.

## Precondition
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
- `src/continuous_refactoring/__init__.py` uses `collect_package_exports(...)` to build `__all__`.
- Explicit module descriptor is ordered and intentionally named.
- `continuous_refactoring.__all__` still includes current public surface in the same order after import.
- Duplicate handling remains compatible with current behavior.
- No production files outside this migration scope are modified.
- Shippability gates pass:
  - `uv run pytest tests/test_continuous_refactoring.py`
  - `uv run python -m continuous_refactoring --help`
  - cluster module import smoke in `continuous_refactoring`.

## Validation steps
1. `uv run pytest tests/test_continuous_refactoring.py`
2. `uv run python -m continuous_refactoring --help`
3. `uv run python - <<'PY'`
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
print("phase-2-shippability-ok", len(continuous_refactoring.__all__))
```
4. `rg -n "collect_package_exports\\(" src/continuous_refactoring/__init__.py`
