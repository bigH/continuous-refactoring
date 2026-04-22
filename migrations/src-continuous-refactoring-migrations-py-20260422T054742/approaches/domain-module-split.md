# Domain Module Split

## Strategy

Split `migrations.py` into two public domain modules and update call sites directly:

- `src/continuous_refactoring/migration_manifest.py`
  - `MigrationManifest`
  - `PhaseSpec`
  - `MIGRATION_STATUSES`
  - `load_manifest()`
  - `save_manifest()`
- `src/continuous_refactoring/migrations.py`
  - migration directory helpers
  - phase cursor/completion operations
  - wake-up eligibility operations

This is a stronger FQN cleanup than the codec-boundary approach. A reader importing `continuous_refactoring.migration_manifest.MigrationManifest` gets the data contract, while `continuous_refactoring.migrations` remains a small module for live migration operations.

No compatibility facade should remain. Update imports in `planning.py`, `phases.py`, `migration_tick.py`, `prompts.py`, `cli.py`, and tests in the same phase.

## Tradeoffs

Pros:
- Produces the cleanest public names if manifest persistence is considered its own domain.
- Makes `migrations.py` much smaller and less mixed.
- Reduces future temptation to add more schema parsing to the operational module.
- Forces tests to reveal which behavior is manifest storage versus migration flow.

Cons:
- Higher churn: many call sites currently import dataclasses and helpers from `continuous_refactoring.migrations`.
- Public package export uniqueness needs deliberate handling.
- The new FQN is arguably verbose for a small project.
- Moving dataclasses can create import cycles if phase cursor helpers still depend on the manifest module and codec code reaches back into `migrations.py`.

## Estimated Phases

1. **Map imports and ownership**
   - Classify every current `continuous_refactoring.migrations` import as manifest contract, path helper, phase cursor, or scheduling.
   - Write the destination list into the phase doc before moving code.

2. **Create manifest module**
   - Move dataclasses, status literals, manifest validation, and load/save functions into `migration_manifest.py`.
   - Keep full-path imports.
   - Update `__init__._SUBMODULES` and ensure no duplicate exported symbols.

3. **Retarget operational modules**
   - Update `planning.py`, `phases.py`, `migration_tick.py`, `prompts.py`, `cli.py`, and tests to import from the new module directly.
   - Leave `migrations.py` with path helpers and pure migration state operations only.

4. **Contract sweep**
   - Run `uv run pytest tests/test_migrations.py tests/test_planning.py tests/test_phases.py tests/test_loop_migration_tick.py tests/test_focus_on_live_migrations.py`.
   - Run full `uv run pytest`.
   - Update `AGENTS.md` if any read-first pointers or load-bearing line references shift.

## Risk Profile

Medium. The end state is neat, but the blast radius is broader than the behavior change warrants.

Main watch-outs:
- Do not leave `migrations.py` as a re-export compatibility layer.
- Avoid a vague module name like `manifest.py`; `migration_manifest.py` keeps the FQN meaningful.
- Watch for circular imports between manifest loading and phase cursor operations.
- Keep legacy manifest compatibility intact.

## Best Fit

Choose this if the migration is meant to improve public module boundaries, not just shrink one file. It is a good second migration after the codec boundary proves stable.
