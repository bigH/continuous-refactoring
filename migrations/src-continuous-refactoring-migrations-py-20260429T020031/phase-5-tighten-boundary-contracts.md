# Phase 5: Tighten Boundary Contracts

## Scope
- `src/continuous_refactoring/migrations.py`
- `src/continuous_refactoring/migration_manifest_ops.py`
- `src/continuous_refactoring/migration_manifest_codec.py`
- `tests/test_migrations.py`
- Any directly affected downstream tests from earlier phases

required_effort: medium
effort_reason: boundary cleanup can accidentally change error semantics or public exports

## Precondition
Phase 4 is complete, all planned internal callers now import extracted
operational helpers from `migration_manifest_ops.py`, and `migrations.py` still
preserves the locked compatibility export set.

## Instructions
- Remove residual non-boundary operational logic from `migrations.py` that no
  longer belongs there after the extraction and caller redirects.
- Keep error translation at the real boundaries:
  `load_manifest()` and `save_manifest()` for filesystem and manifest-file I/O,
  `migration_manifest_codec.py` for payload decoding and encoding semantics.
- Preserve exception nesting with `from error` when translation is warranted.
- Inventory transitional wrappers and duplicate helpers left by the extraction.
  Delete each one unless it is part of the Phase 1 locked export set or is named
  and justified as a downstream contract still used by internal callers.
- Stop short of a hard compatibility cut. If a helper is still part of the
  locked public surface, keep that export from `continuous_refactoring.migrations`.

## Definition of Done
- `migrations.py` reads as a facade for manifest concepts, manifest-path
  helpers, manifest I/O boundaries, and compatibility exports rather than as
  the primary implementation home for extracted operational logic.
- Filesystem and JSON failures are wrapped once at the true boundary, with
  preserved nested causes.
- No dead transitional code remains from the split, except compatibility
  exports in the Phase 1 locked export set or named downstream contracts with
  an explicit retention reason.
- The locked compatibility export set from Phase 1 still passes unchanged.
- The configured broad validation command passes.

## Validation
- Run `uv run pytest tests/test_migrations.py`.
- Run any focused downstream suites affected by the final boundary cleanup,
  expected to include `uv run pytest tests/test_phases.py tests/test_planning.py
  tests/test_loop_migration_tick.py tests/test_prompts.py`.
- Finish with `uv run pytest`.
