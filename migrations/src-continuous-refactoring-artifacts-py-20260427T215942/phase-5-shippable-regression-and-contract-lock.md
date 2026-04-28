# Phase 5: Cross-module contract lock and migration finalization

## Objective
Lock export/runtime contracts after boundary hardening and complete migration-wide regression validation while keeping the repository shippable after each intermediate step.

## Scope
- `src/continuous_refactoring/__init__.py`
- `src/continuous_refactoring/loop.py`
- `src/continuous_refactoring/migration_tick.py`
- `src/continuous_refactoring/phases.py`
- `src/continuous_refactoring/config.py`
- `src/continuous_refactoring/git.py`
- `src/continuous_refactoring/agent.py`
- `src/continuous_refactoring/artifacts.py`
- All tests touched in earlier phases
- `tests/test_continuous_refactoring.py`
- `tests/test_loop_migration_tick.py`
- `tests/test_phases.py`
- `tests/test_routing.py`
- `tests/test_run.py`
- `tests/test_run_once.py`
- `tests/test_run_once_regression.py`
- `tests/test_cli_init_taste.py`
- `tests/test_cli_taste_warning.py`
- `tests/test_config.py`

## Instructions
1. Verify `__init__.py` still enforces duplicate-export safety after any added/retained symbols and update no public symbol lists unless required by the migration.
2. Re-run phase-level and integration checks to ensure no behavior drift:
   - phase readiness/validation retry semantics,
   - artifact summary/event content,
   - CLI taste/init messages,
   - run/run-once loop outcomes.
3. Confirm migration docs and this plan match scope edits and that no phase introduced behavior outside migration intent, including the current `migration_tick.py` seam covered by `tests/test_loop_migration_tick.py`.
4. If any CLI exit path changed only in wording for more context, add/adjust exact-string assertions in dedicated CLI tests and call this out explicitly in DoD.
5. Verify `migrations/src-continuous-refactoring-artifacts-py-20260427T215942/manifest.json` phase graph and metadata remain consistent with this plan (no missing or renamed phase files).

## Precondition
- Phase 4 complete and green.
- `tests/test_continuous_refactoring.py` and phase-3/4 targeted suites pass.
- All intended phase edits are present in working tree.
- All phase documents in this migration directory match their intended scope (especially phase names referenced in `manifest.json`).

## Definition of Done
- Package export checks are clean for touched modules.
- All phase-level target validations and full suite are green.
- Boundary-cause semantics are consistent across `artifacts`, `agent`, `git`, `loop`, `migration_tick`, `phases`, `config`, and CLI callsites.
- Migration scope and docs are aligned to the final code shape.
- `manifest.json` and `plan.md` are coherent with delivered phase files and scope.
- No unresolved documentation/process debt introduced by this migration.

## Validation steps
- `uv run pytest tests/test_config.py tests/test_continuous_refactoring.py tests/test_loop_migration_tick.py tests/test_phases.py tests/test_routing.py`
- `uv run pytest tests/test_cli_init_taste.py tests/test_cli_taste_warning.py tests/test_run_once.py tests/test_run_once_regression.py`
- `uv run pytest tests/test_run.py`
- `uv run pytest`
