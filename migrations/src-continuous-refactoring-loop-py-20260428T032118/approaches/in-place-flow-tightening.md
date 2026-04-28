# In-Place Loop Flow Tightening

## Strategy

Keep `src/continuous_refactoring/loop.py` as the public home of run orchestration and make it less awful without changing module boundaries.

- Reshape private flow so `run_once()`, `run_loop()`, and `run_migrations_focused_loop()` read top-down.
- Extract only short, domain-truthful helpers for repeated branches:
  - baseline/setup
  - target action execution
  - migration probe execution
  - retry loop execution
- Keep `_finalize_commit`, effort logging, preserved-workspace handling, and CLI-facing entrypoints in `loop.py`.
- Prefer deleting tiny one-off branches over introducing generic abstractions.

## Tradeoffs

Pros:
- Lowest blast radius. Imports, monkeypatch targets, and package exports stay stable.
- Best fit if the real pain is readability, not module ownership.
- Least risk of breaking `run_once` / `run` / focused-migration semantics that already have heavy test coverage.

Cons:
- `loop.py` stays large.
- Mixed responsibilities remain: baseline validation, routing, migration probing, retry control, and sleep/commit mechanics still live together.
- Future structural work will still have to cut the file apart later.

## Estimated Phases

1. Characterize current flow in tests.
   `required_effort: low`
   - Add or tighten regression coverage around:
   - `run_once()` direct-refactor path vs routed migration/planning path.
   - `run_loop()` migration-first selection, retry exhaustion, and preserved live-migration restoration.
   - `run_migrations_focused_loop()` eligibility filtering and stop conditions.

2. Extract shared local helpers inside `loop.py`.
   `required_effort: medium`
   - Pull repeated setup/finalization branches into small private helpers.
   - Keep helper count low and names specific to runner flow.
   - Remove duplicated logging/branching where the behavior is already identical.

3. Normalize the three top-level loops around the same internal shape.
   `required_effort: medium`
   - Make each entrypoint read as setup -> route/execute -> finalize.
   - Keep behavior unchanged, especially around revert, commit ownership, and action counting.

4. Validate broadly.
   `required_effort: low`
   - `uv run pytest tests/test_run_once.py tests/test_run.py tests/test_loop_migration_tick.py tests/test_focus_on_live_migrations.py`
   - `uv run pytest`

## Risk Profile

Low.

Main risks:
- “Cleanup” can become abstraction confetti if helper extraction gets cute.
- Shared branches may look identical but differ in artifact logging or revert timing.

Mitigations:
- Keep helpers narrow and behavior-preserving.
- Treat printed output, artifact events, and commit/revert semantics as contract, not noise.

## Best Fit

Choose this when the migration should stay safe and incremental, and the goal is to make `loop.py` readable before deciding whether a real split is worth it.
