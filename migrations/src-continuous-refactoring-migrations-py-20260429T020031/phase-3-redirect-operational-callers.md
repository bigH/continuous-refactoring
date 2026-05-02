# Phase 3: Redirect Operational Callers

## Scope
- `src/continuous_refactoring/phases.py`
- `src/continuous_refactoring/loop.py`
- `src/continuous_refactoring/prompts.py`
- `src/continuous_refactoring/migration_tick.py`
- `src/continuous_refactoring/migrations.py`
- `src/continuous_refactoring/migration_manifest_ops.py`
- Related tests for touched call sites:
  `tests/test_phases.py`, `tests/test_loop_migration_tick.py`,
  `tests/test_focus_on_live_migrations.py`, `tests/test_prompts.py`,
  `tests/test_run.py`, `tests/test_migrations.py`

required_effort: medium
effort_reason: runtime and scheduling import rewrites carry real behavior risk

## Precondition
Phase 2 is complete, `migration_manifest_ops.py` owns the extracted operational
helpers, and `migrations.py` still re-exports those helpers through the locked
compatibility surface.

## Instructions
- Redirect the operational callers that consume extracted helpers today:
  `src/continuous_refactoring/phases.py`,
  `src/continuous_refactoring/loop.py`,
  `src/continuous_refactoring/prompts.py`, and
  `src/continuous_refactoring/migration_tick.py`.
- Move those modules to direct imports from
  `continuous_refactoring.migration_manifest_ops` only for helpers extracted in
  Phase 2, such as `complete_manifest_phase`, `resolve_current_phase`,
  `phase_file_reference`, `bump_last_touch`, `eligible_now`, and
  `has_executable_phase`.
- Keep `continuous_refactoring.migrations` as the public compatibility facade.
  Public imports and tests that intentionally exercise the shipped surface stay
  on that module.
- Do not edit `review_cli.py` or `migration_cli.py` in this phase. They are
  real remaining consumers, but they are intentionally deferred to the next
  lower-risk phase.
- Preserve helper names unless a rename is strictly necessary and covered by
  updated tests.

## Definition of Done
- `phases.py`, `loop.py`, `prompts.py`, and `migration_tick.py` import their
  extracted operational helpers directly from `migration_manifest_ops.py`.
- `review_cli.py` and `migration_cli.py` remain on the compatibility facade and
  are the only planned remaining internal consumers of these extracted helpers
  after this phase.
- `tests/test_migrations.py` still exercises the compatibility facade through
  `continuous_refactoring.migrations`.
- The redirect introduces no circular import and no duplicate helper wrappers.
- The configured broad validation command passes.

## Validation
- Run the focused caller tests first:
  `uv run pytest tests/test_phases.py tests/test_loop_migration_tick.py
  tests/test_focus_on_live_migrations.py tests/test_prompts.py tests/test_run.py`
- Run `uv run pytest tests/test_migrations.py` to keep the compatibility facade
  honest.
- Finish with `uv run pytest`.
