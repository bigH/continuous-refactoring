# Phase 3: Redirect Internal Callers

## Scope
- `src/continuous_refactoring/phases.py`
- `src/continuous_refactoring/loop.py`
- `src/continuous_refactoring/prompts.py`
- `src/continuous_refactoring/migrations.py`
- Related tests for touched call sites:
  `tests/test_phases.py`, `tests/test_loop_migration_tick.py`,
  `tests/test_focus_on_live_migrations.py`, `tests/test_prompts.py`,
  `tests/test_run.py`, `tests/test_migrations.py`

required_effort: medium
effort_reason: import rewrites span several call sites and can hide behavior drift

## Precondition
Phase 2 is complete, `migration_manifest_ops.py` owns the extracted operational
helpers, and `migrations.py` still re-exports those helpers through the locked
compatibility surface.

## Instructions
- Redirect only the in-scope internal callers that consume extracted
  operational helpers:
  `src/continuous_refactoring/phases.py`,
  `src/continuous_refactoring/loop.py`, and
  `src/continuous_refactoring/prompts.py`.
- Move those modules to direct imports from
  `continuous_refactoring.migration_manifest_ops` only for helpers extracted in
  Phase 2, such as `complete_manifest_phase`, `resolve_current_phase`, and
  `phase_file_reference`.
- Do not edit `planning.py` or `cli.py` in this phase unless Phase 2 made a
  narrow coherence fix unavoidable. They are in the migration scope, but they
  are not required caller redirects for this phase.
- Keep `continuous_refactoring.migrations` as the public compatibility facade.
  Public imports and tests that intentionally exercise the shipped surface stay
  on that module.
- Preserve helper names unless a rename is strictly necessary and covered by
  updated tests.

## Definition of Done
- `phases.py`, `loop.py`, and `prompts.py` import their extracted operational
  helpers directly from `migration_manifest_ops.py`.
- `tests/test_migrations.py` still exercises the compatibility facade through
  `continuous_refactoring.migrations`.
- No out-of-scope source modules were edited just to widen the redirect.
- The redirect introduces no circular import and no duplicate helper wrappers.
- The configured broad validation command passes.

## Validation
- Run the focused caller tests first:
  `uv run pytest tests/test_phases.py tests/test_loop_migration_tick.py
  tests/test_focus_on_live_migrations.py tests/test_prompts.py tests/test_run.py`.
- Run `uv run pytest tests/test_migrations.py` to keep the compatibility facade
  honest.
- Finish with `uv run pytest`.
