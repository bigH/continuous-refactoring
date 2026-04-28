# Phase 1: Export contract baseline

## Objective
Lock current package-surface expectations in executable tests before changing `__init__.py` internals.

## Scope
- `tests/test_continuous_refactoring.py`

## Instructions
1. Split existing package contract assertions into explicit checks for:
   - `continuous_refactoring.__all__` type and tuple ordering
   - uniqueness of exported names
   - known public symbol presence
   - internal members from `migration_manifest_codec` not exported at package root
2. Keep all behavior unchanged in production code for this phase.
3. Keep assertions focused on outcome, not implementation shape.

## Precondition
- `test -z "$(git diff -- src/continuous_refactoring/__init__.py)"` (baseline `__init__.py` untouched)
- `test -f approaches/init-init-export-surface.md`
- `uv run pytest tests/test_continuous_refactoring.py`
- `uv run python -m continuous_refactoring --help`
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
- `tests/test_continuous_refactoring.py` contains explicit package-surface assertions for all baseline contract points above.
- No production source files changed in this phase.
- Shippability gates pass:
  - `uv run pytest tests/test_continuous_refactoring.py`
  - `uv run python -m continuous_refactoring --help`
  - `continuous_refactoring` import smoke for package and local cluster modules.

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
print("phase-1-shippability-ok", len(continuous_refactoring.__all__))
```
