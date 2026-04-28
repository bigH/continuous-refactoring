# Approach: Lightweight Domain Split of Artifact Subsystems

## Strategy
- Keep API compatibility but split `artifacts.py` into two files:
  - `src/continuous_refactoring/artifacts_models.py` for immutable telemetry data structures.
  - `src/continuous_refactoring/artifact_runs.py` for run lifecycle creation and atomic writes.
  - `src/continuous_refactoring/artifacts.py` as a thin compatibility re-export and doc seam.
- Keep CLI/migration and loop integration untouched where possible:
  - `loop.py`, `phases.py`, `migration_tick.py`, `routing_pipeline.py`, `agent.py`, `config.py`, `git.py`, `cli.py`.
- Replace ad hoc imports of `ContinuousRefactorError` from `artifacts.py` with direct imports from `artifacts.py` compatibility alias only if needed.
- This creates clearer file-level domains while preserving FQNs and avoiding module sprawl.

## Tradeoffs
- Cleaner local module focus and lower future merge pain when `artifacts.py` starts to grow.
- Best future extensibility for migration state persistence versus command-capture concerns.
- Highest mechanical risk of this set due split and import graph migration.
- Increases short-term review burden because many names stay re-exported for compatibility.
- Must guard against hidden behavior shifts due import order and module initialization.

## Estimated phases
1. Create split modules with zero-behavior shims and compatibility exports
2. Migrate production imports and keep package `__all__` uniqueness clean
3. Fold in taste-compliant error wrapping and cause chaining during migration
4. Update tests to use compatibility imports and assert no drift in summaries/events
5. Run full suite after phased import migration and clean dead-paths

### Phase intent
- Phase 1: Data models and lifecycle utilities move out without changing logic.
- Phase 2: Rewire imports in cluster modules and ensure `continuous_refactoring.__all__` contract remains stable.
- Phase 3: Apply error-boundary pass without introducing interface churn.
- Phase 4: Remove transitional names and dead compatibility comments only if no longer needed.
- Phase 5: Verification as per existing full-run migration gate.

## Risk profile
- Technical risk: medium
- Blast radius: high
- Failure modes:
  - Package import order regressions while `__init__.py` rebuilds re-exports.
  - Hidden test failures due import-time side effects.
  - More difficult conflict detection with duplicate symbols during package init.

## Why pick this only if we can absorb the churn
- Strong structure win, but not worth it if we need the cleanest, fastest path to safe artifact boundary improvement.
