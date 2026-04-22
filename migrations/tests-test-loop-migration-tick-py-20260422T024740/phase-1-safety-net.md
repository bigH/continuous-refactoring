# Phase 1: Safety Net

## Objective

Lock down migration tick behavior before moving it out of `routing_pipeline.py`.

This phase is tests-only. If a new or tightened test exposes a production bug, stop and add a separate fix phase before extraction.

## Precondition

`try_migration_tick()` and `enumerate_eligible_manifests()` are still implemented and exported by `continuous_refactoring.routing_pipeline`, `tests/test_loop_migration_tick.py` still monkeypatches that boundary, no `src/continuous_refactoring/migration_tick.py` module exists, and the focused migration tick tests pass.

## Scope

Allowed files:

- `tests/test_loop_migration_tick.py`
- `tests/test_focus_on_live_migrations.py`
- `tests/test_scope_loop_integration.py`

Optional only if an existing test helper name or fixture shape blocks clear tests:

- `tests/conftest.py`

Do not edit production code in this phase.

## Instructions

1. Add or tighten tests for eligible manifest enumeration:
   - missing live directory returns no candidates;
   - non-directory and `__*` entries are ignored;
   - manifests without executable phases are ignored;
   - eligible candidates are sorted by `created_at`.
2. Add or tighten tests for ready-check error handling:
   - `check_phase_ready()` raising `ContinuousRefactorError` returns `outcome == "abandon"`;
   - the decision record uses `call_role == "phase.ready-check"`;
   - the summary is sanitized through the existing decision helpers.
3. Add or tighten tests for ready phase execution:
   - `execute_phase()` receives runtime taste, validation command, retry budget, and agent settings;
   - successful execution calls `finalize_commit()` with the phase file reference, not a numeric cursor;
   - failed execution returns `abandon` and preserves `retry_used`.
4. Add or tighten tests for not-ready and unverifiable phases:
   - `no` bumps `last_touch`, sets `cooldown_until`, sets `wake_up_on` only when absent, and falls through as `not-routed`;
   - `unverifiable` persists human-review fields and returns `blocked`;
   - `execute_phase()` is not called for either verdict.
5. Keep tests outcome-oriented. Monkeypatch only real current boundaries: `check_phase_ready`, `execute_phase`, `finalize_commit`, classifier fallthrough, and the live migrations directory resolver.

## Definition of Done

- Focused tests cover enumeration, ready-check failure, ready execution success/failure, deferral, and human-review blocking at the current `routing_pipeline` boundary.
- No production files are changed.
- No new module or public symbol has been introduced.
- Existing production behavior and monkeypatch paths remain stable.
- The repository is shippable after this phase.

## Validation

Run:

```sh
uv run pytest tests/test_loop_migration_tick.py
uv run pytest tests/test_focus_on_live_migrations.py tests/test_scope_loop_integration.py
```
