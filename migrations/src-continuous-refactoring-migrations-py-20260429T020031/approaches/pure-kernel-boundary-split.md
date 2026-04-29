# Approach: Pure Kernel + Boundary Split

## Strategy
- Separate migration manifest logic into a pure kernel and an impure boundary:
  - `src/continuous_refactoring/migration_manifest.py`: dataclasses, status constants, phase traversal, eligibility, and completion helpers.
  - `src/continuous_refactoring/migration_manifest_store.py`: `load_manifest` and `save_manifest` only.
  - `src/continuous_refactoring/migration_manifest_codec.py`: payload schema translation only.
  - `src/continuous_refactoring/migrations.py`: compatibility facade plus path helpers, or a thin redirect layer that can later shrink away.
- Lean into code shape: pure functions get dense example/property-style coverage, boundary code gets example-based failure tests.
- Treat public import changes as compatibility-sensitive even though the implementation is being aggressively cleaned up underneath.

## Tradeoffs
- Cleanest architecture. The module names finally tell the truth.
- Best testing shape: pure manifest behavior becomes cheap to reason about and validate.
- Highest churn and most opportunities for circular imports, stale exports, and half-finished compatibility shims.
- Very easy to overbuild. If the split does not materially simplify call sites, it’s architecture cosplay.

## Estimated phases
1. Add package-surface and behavior lock tests for manifest types, ops helpers, and boundary errors.
   - `required_effort`: `medium`
2. Create `migration_manifest.py` and move pure datatypes plus cursor/eligibility/completion logic there.
   - `required_effort`: `medium`
3. Create `migration_manifest_store.py` for filesystem I/O and keep `migration_manifest_codec.py` focused on schema conversion.
   - `required_effort`: `high`
4. Rewire `planning.py`, `phases.py`, `migration_tick.py`, `loop.py`, and tests to the new structure while preserving stable public imports where they are still worth keeping.
   - `required_effort`: `high`
5. Review whether `migrations.py` still earns its existence or should remain only as a compatibility facade for one release window.
   - `required_effort`: `xhigh`

## Risk profile
- Technical risk: medium to high
- Blast radius: high
- Failure modes:
  - Import cycles or package boot failures, especially because codec currently imports dataclasses from `migrations.py`.
  - Accidental contract changes around manifest loading, error messages, or saved JSON formatting.
  - Over-splitting that makes call sites noisier instead of clearer.

## Best when
- We want the end-state architecture now and are willing to pay the migration cost.
- The repo is about to do more substantial migration-system work, making a stronger boundary immediately valuable.
