# Phase 3: Origin-aware duplicate-symbol diagnostics

## Objective
Improve duplicate-export failure diagnostics so collisions include where each symbol originated, while preserving non-duplicate behavior.

## Scope
- `src/continuous_refactoring/__init__.py`
- `tests/test_continuous_refactoring.py`

## Instructions
1. Update the collector helper to return origin-aware diagnostics for duplicate symbols.
2. Keep duplicate error class compatibility and raise signal stable (`RuntimeError` contract remains unchanged).
3. Include module provenance in duplicate messages:
   - symbol name
   - original module
   - conflicting module
4. Add tests for both:
   - duplicate detection with provenance
   - non-duplicate path remains unchanged

## Precondition
- `rg -n "def collect_package_exports\\(" src/continuous_refactoring/__init__.py` succeeds.
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
- Duplicate-symbol failure in `collect_package_exports` includes both module origins and symbol identity.
- Non-duplicate symbol collection output is behaviorally unchanged.
- `tests/test_continuous_refactoring.py` covers duplicate provenance and baseline success cases.
- Repo remains shippable according to all reusable checks.

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
print("phase-3-shippability-ok", len(continuous_refactoring.__all__))
```
4. `rg -n "duplicate|already exported|module" src/continuous_refactoring/__init__.py`
