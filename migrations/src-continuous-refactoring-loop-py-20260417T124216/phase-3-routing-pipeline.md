# Phase 3 — Extract `routing_pipeline.py`

## Goal

Move routing, migration-tick, and scope-expansion orchestration out of
`loop.py` into `src/continuous_refactoring/routing_pipeline.py`.

This is the largest remaining extraction, but it is still a **bounded move**:
it should relocate the routing pipeline, not redesign the run loop.

**Blocked by:** phase 1. Phase 2 is not a hard code dependency, though the
manifest still queues phase 2 first for a smaller restart step.

## Naming Decision

Keep the existing `routing.py` classifier module and add a sibling
`routing_pipeline.py`.

- `routing.py` = classification
- `routing_pipeline.py` = execution/routing glue

Do not merge them in this phase.

## Scope — Symbols to Move

From `loop.py` to `routing_pipeline.py`:

- `RouteResult` (public)
- `_migration_name_from_target` → `migration_name_from_target` (public)
- `_enumerate_eligible_manifests` → `enumerate_eligible_manifests` (public)
- `_try_migration_tick` → `try_migration_tick` (public)
- `_scope_bypass_context` → stays private: `_scope_bypass_context`
- `_expand_target_for_classification` → `expand_target_for_classification` (public)
- `_route_and_run` → `route_and_run` (public)
- `_describe_planning_outcome` → `describe_planning_outcome` (public)

## Out of Scope

Keep in `loop.py`:

- `_resolve_live_migrations_dir`
- `_finalize_commit`
- `_retry_context`
- `_run_refactor_attempt`
- `run_once`, `run_loop`, `run_migrations_focused_loop`
- `_focus_eligible_manifests`
- baseline / prompt / target-resolution helpers

Phase 3 must not solve circular imports by importing private helpers back from
`loop.py`. If `route_and_run()` or `try_migration_tick()` still need data such
as `live_dir` or a commit-finalizer, pass those in from `loop.py` or define new
private helpers inside `routing_pipeline.py`.

## Instructions

1. Create `src/continuous_refactoring/routing_pipeline.py` with a one-line
   module docstring.
2. Move the listed symbols.
3. Import the collaborators the new module actually uses directly from their
   owning modules (`decisions`, `routing`, `planning`, `phases`,
   `scope_expansion`, `migrations`, `git`, and any config helpers needed for
   local private helpers).
4. Update `loop.py` to call the extracted public surface. If needed to avoid a
   cycle, let `loop.py` provide already-resolved inputs such as `live_dir` or a
   finalize callback instead of keeping hidden back-edges into `loop.py`.
5. Update test imports and monkeypatch targets in the same commit. Grep at
   least:
   - `tests/test_scope_loop_integration.py`
   - `tests/test_loop_migration_tick.py`
   - `tests/test_focus_on_live_migrations.py`
   - `tests/test_no_driver_branching.py`
   - routing-focused cases in `tests/test_run.py`
6. Move the affected monkeypatch targets/imports from
   `continuous_refactoring.loop` to `continuous_refactoring.routing_pipeline`
   for the symbols extracted here (`RouteResult`, `route_and_run`,
   `try_migration_tick`, `enumerate_eligible_manifests`,
   `expand_target_for_classification`, `migration_name_from_target`, and any
   imported collaborators such as `classify_target`, `run_planning`,
   `check_phase_ready`, or `execute_phase` that are patched where the new module
   looks them up).

## Precondition

`phase-1-decisions.md` is complete.

## Definition of Done

- `src/continuous_refactoring/routing_pipeline.py` exists and owns the listed
  routing helpers.
- `loop.py` no longer defines any symbol moved in this phase.
- The tests listed above pass with updated imports/monkeypatch targets.
- `grep -rn "loop\._\(try_migration_tick\|enumerate_eligible_manifests\|expand_target_for_classification\|route_and_run\|describe_planning_outcome\|migration_name_from_target\)" src tests` returns nothing.
- `uv run pytest` is green.
- `routing_pipeline.py` lands roughly in the 350–500 line range.
- On the normal path where phase 2 has already landed, `loop.py` should be
  roughly 1000–1150 lines after this phase. Do not claim ~500 here.

## Validation Steps

1. `uv run pytest tests/test_scope_loop_integration.py tests/test_loop_migration_tick.py tests/test_focus_on_live_migrations.py tests/test_no_driver_branching.py`
2. `uv run pytest tests/test_run.py tests/test_run_once.py tests/test_run_once_regression.py`
3. `uv run pytest`
4. `python -m continuous_refactoring --help`
5. `wc -l src/continuous_refactoring/loop.py src/continuous_refactoring/routing_pipeline.py`
6. Grep for stale `continuous_refactoring.loop` references to the moved symbols.

## Risk & Rollback

Highest-risk remaining phase: largest extraction and the most monkeypatch churn.
Run the full suite before considering it done. Rollback: `git reset --hard
HEAD~1`.
