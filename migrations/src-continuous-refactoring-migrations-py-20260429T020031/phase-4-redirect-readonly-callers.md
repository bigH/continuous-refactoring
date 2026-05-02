# Phase 4: Redirect Read-Only Callers

## Scope
- `src/continuous_refactoring/review_cli.py`
- `src/continuous_refactoring/migration_cli.py`
- `src/continuous_refactoring/migrations.py`
- `src/continuous_refactoring/migration_manifest_ops.py`
- Related tests for touched call sites:
  `tests/test_cli_review.py`, `tests/test_migrations.py`
- Read-only adjacencies only if needed for coherence:
  `tests/test_continuous_refactoring.py`

required_effort: low
effort_reason: the remaining redirects are import-only in read-only CLI flows

## Precondition
Phase 3 is complete, the runtime and scheduling callers already import
extracted helpers from `migration_manifest_ops.py`, and `review_cli.py` plus
`migration_cli.py` are the remaining internal consumers intentionally left on
the compatibility facade.

## Instructions
- Redirect `src/continuous_refactoring/review_cli.py` and
  `src/continuous_refactoring/migration_cli.py` to direct imports from
  `continuous_refactoring.migration_manifest_ops` for extracted helpers they
  consume today, notably `phase_file_reference` and `resolve_current_phase`.
- Keep `load_manifest()` and the public manifest types on
  `continuous_refactoring.migrations` where that remains the clearer boundary.
- Do not widen this phase into general CLI cleanup. It exists to finish the
  honest internal caller redirect set before the boundary cleanup phase.
- Preserve command behavior, user-visible wording, and migration target
  resolution semantics.

## Definition of Done
- `review_cli.py` and `migration_cli.py` import their extracted operational
  helpers directly from `migration_manifest_ops.py`.
- No known internal caller still depends on `continuous_refactoring.migrations`
  for helpers moved in Phase 2, aside from deliberate compatibility tests.
- CLI behavior and output remain unchanged.
- The configured broad validation command passes.

## Validation
- Run `uv run pytest tests/test_cli_review.py tests/test_migrations.py`.
- If package-root export coverage moved, run
  `uv run pytest tests/test_continuous_refactoring.py`.
- Finish with `uv run pytest`.
