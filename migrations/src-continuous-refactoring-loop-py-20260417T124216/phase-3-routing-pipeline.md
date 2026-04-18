# Phase 3 — Extract `routing_pipeline.py`

## Goal

Move the routing / migration-tick / scope-expansion glue out of `loop.py` into
`src/continuous_refactoring/routing_pipeline.py`. This is the largest extraction
by line count and gives `loop.py` back its focus on `run_once`/`run_loop`
orchestration.

**Blocked by:** phases 1 and 2 (imports `decisions.*` and `failure_report.*`).

## Naming Decision

The approach doc flags mild naming overlap with the existing `routing.py`
(classifier). Resolution: **keep `routing.py` as-is and add a sibling
`routing_pipeline.py`**. Do NOT fold them — `routing.py` is a pure classifier;
`routing_pipeline.py` orchestrates execution. Distinct responsibilities earn
distinct modules. Revisit only if `routing_pipeline.py` shrinks below ~150
lines after phase 4, at which point a `routing/` package could absorb both.

## Scope — Symbols to Move

From `loop.py` to `routing_pipeline.py`:

- `RouteResult` (dataclass, ~line 168) → `RouteResult` (public)
- `_try_migration_tick` → `try_migration_tick` (public)
- `_enumerate_eligible_manifests` → `enumerate_eligible_manifests` (public)
- `_expand_target_for_classification` → `expand_target_for_classification` (public)
- `_route_and_run` → `route_and_run` (public)
- `_scope_bypass_context` → stays private: `_scope_bypass_context`
- `_describe_planning_outcome` → `describe_planning_outcome` (public)
- `_migration_name_from_target` → `migration_name_from_target` (public)

## Out of Scope

- `run_once`, `run_loop`, `run_migrations_focused_loop`,
  `_focus_eligible_manifests`, `_run_refactor_attempt`, `run_baseline_checks`,
  arg-parsing helpers, `_finalize_commit`, `_retry_context`,
  `_load_taste_safe`, `_resolve_live_migrations_dir` — all stay in `loop.py`.
  `run_migrations_focused_loop` is orchestration (calls
  `run_baseline_checks`, `prepare_run_branch`, `require_clean_worktree`) and
  belongs with `run_once`/`run_loop`. `_focus_eligible_manifests` is a thin
  filter over `enumerate_eligible_manifests` kept co-located with its sole
  caller. Both MUST be carried through phase 3 unchanged — update their call
  sites from `_enumerate_eligible_manifests` / `_try_migration_tick` to the
  new FQNs `routing_pipeline.enumerate_eligible_manifests` /
  `routing_pipeline.try_migration_tick`.

## Instructions

1. Create `src/continuous_refactoring/routing_pipeline.py`. One-line docstring.
2. Move the listed symbols. Imports required inside the new module:
   `continuous_refactoring.decisions`, `continuous_refactoring.failure_report`,
   `continuous_refactoring.routing` (classifier), `continuous_refactoring.phases`,
   `continuous_refactoring.scope_expansion`, `continuous_refactoring.migrations`,
   `continuous_refactoring.targeting`, `continuous_refactoring.git`. Verify
   each via grep.
3. In `loop.py`, import the public surface:
   `from continuous_refactoring.routing_pipeline import try_migration_tick, route_and_run, RouteResult, migration_name_from_target`.
4. Update `tests/test_loop_migration_tick.py` and
   `tests/test_focus_on_live_migrations.py` — every monkeypatch currently on
   `continuous_refactoring.loop.<symbol>` that targets a moved symbol must
   move to `continuous_refactoring.routing_pipeline.<new_name>`. Specifically
   verified targets to update: `classify_target` (if patched via loop — check),
   `check_phase_ready`, `execute_phase`, `_try_migration_tick` (three
   monkeypatches in `test_focus_on_live_migrations.py` → `try_migration_tick`
   on routing_pipeline), `_resolve_live_migrations_dir` (stays on `loop` —
   don't move).
5. No re-exports in `loop.py`. Taste: no shims in non-shipped code.

## Ready When

- `routing_pipeline.py` exists with the listed public surface.
- `loop.py` no longer defines any moved symbol.
- `tests/test_loop_migration_tick.py` passes with updated monkeypatch paths.
- `grep -rn "loop\._\(try_migration_tick\|enumerate_eligible_manifests\|expand_target_for_classification\|route_and_run\|describe_planning_outcome\|migration_name_from_target\)" src tests` — empty.
- `loop.py` down to roughly 500–600 lines; `routing_pipeline.py` 300–450 lines.
- `pytest` green.

## Validation Steps

1. `pytest -x` with emphasis on `tests/test_loop_migration_tick.py`,
   `tests/test_run_once.py`, `tests/test_scope_loop_integration.py`.
2. `python -m continuous_refactoring --help`.
3. End-to-end smoke: `pytest tests/test_e2e.py`.
4. `wc -l src/continuous_refactoring/loop.py src/continuous_refactoring/routing_pipeline.py`.
5. Confirm no symbol appears in both `loop.py` and `routing_pipeline.py`:
   `diff <(grep -E "^(def|class) " src/continuous_refactoring/loop.py | awk '{print $2}') <(grep -E "^(def|class) " src/continuous_refactoring/routing_pipeline.py | awk '{print $2}')` should report no overlap.

## Risk & Rollback

Highest-risk phase — largest move, most test monkeypatch churn. Run the full
suite before opening the PR. Rollback: `git reset --hard HEAD~1`.
