# Phase 4: Package Sweep And Broad Validation

## Objective
Finalize the internal module boundary, update package or repo-contract wiring only if the new module requires it, and run the broad regression sweep that proves the extraction shipped cleanly.

## Scope
- `src/continuous_refactoring/refactor_attempts.py`
- `src/continuous_refactoring/loop.py`
- `src/continuous_refactoring/__init__.py` only if package import wiring must acknowledge the new module
- `tests/test_continuous_refactoring.py` only if package-surface expectations change
- `tests/test_run.py`
- `tests/test_run_once.py`
- `tests/test_run_once_regression.py`
- `tests/test_loop_migration_tick.py`
- `AGENTS.md` only if the added module makes repo-contract statements stale

## Instructions
1. Update package wiring only if needed for the new internal module to participate correctly in package import checks. Keep `refactor_attempts.py` internal unless there is an existing package-surface reason to expose it.
2. If `src/continuous_refactoring/__init__.py` changes, update `tests/test_continuous_refactoring.py` in the same phase so package-surface expectations remain explicit.
3. Update `AGENTS.md` in the same phase if its module-layout or load-bearing guidance became stale after adding `refactor_attempts.py`.
4. Remove dead imports, dead helper code, and stale test scaffolding left behind by the extraction. Do not leave compatibility cruft.
5. Run the targeted package/import checks first, then the full pytest suite. Fix only fallout that belongs to this migration boundary.

required_effort: low
effort_reason: This phase is mostly cleanup and validation once the structural risk is already retired.

## Precondition
- Phase 3 is complete.
- `refactor_attempts.py` is the active implementation for preserved-workspace reset and retryable refactor attempts.
- Package-surface updates, test expectation updates, and repo-contract cleanup are the only remaining scoped work in this migration.

## Definition of Done
- Package import still succeeds, and if `__init__.py` changed, `tests/test_continuous_refactoring.py` explicitly reflects the new expectation.
- `refactor_attempts.py` remains an internal module unless this phase deliberately and explicitly changes the package surface.
- `AGENTS.md` matches the live repo if the migration changed any load-bearing statement it contains.
- No dead extraction scaffolding or stale imports remain in the touched files.
- The targeted package/import validation and the full pytest suite both pass.
- The repository remains shippable at the final migration checkpoint.

## Validation
- Run `uv run pytest tests/test_continuous_refactoring.py tests/test_run.py tests/test_run_once.py tests/test_run_once_regression.py tests/test_loop_migration_tick.py`.
- Run `uv run pytest`.
