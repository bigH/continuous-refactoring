# Split Driver Router Boundary

## Strategy

Make `loop.py` a thinner driver by pulling route-result handling and migration/fallback branching into routing-facing helpers. The current target test drives `continuous_refactoring.run_once`, but most assertions are really about how the driver reacts to migration tick outcomes: commit, blocked, deferred, and not-routed fallthrough. This approach cleans the driver/router contract so `run_once`, `run_loop`, and `run_migrations_focused_loop` all interpret migration outcomes consistently.

This is broader than extracting migration tick alone. It treats the problem as an orchestration boundary issue, with `loop.py` owning CLI run lifecycle and `routing_pipeline.py` owning routing decisions plus decision records.

## What Changes

- Introduce a small result-handling helper or dataclass in `routing_pipeline.py` that exposes the final action needed by the driver.
- Reduce repeated `if route_result.outcome == ...` blocks in `run_once` and `run_loop`.
- Align focused-loop handling of `"not-routed"` deferred records with the same result semantics where practical.
- Update `tests/test_loop_migration_tick.py` to assert the public driver outcomes while reducing monkeypatch depth.
- Keep phase execution and manifest mutation in existing modules; this approach reshapes control flow, not domain storage.

## Estimated Phases

1. Add or tighten tests for consistent route outcome handling across `run_once`, `run_loop`, and focused migration loop.
2. Introduce the route-result interpretation helper and move one driver path at a time.
3. Apply the same helper to the remaining driver path and prune duplicated branches.
4. Clean the target test harness after production flow is simpler.

## Tradeoffs

- Can reduce duplication in `loop.py`, which is still a large active maintenance target.
- Improves consistency across driver modes.
- Higher blast radius than the test-harness or tick-extraction options because it touches run lifecycle behavior.
- It may collide with ongoing or recently completed `loop.py` migration work. The repo currently references a missing `loop.py` migration in `AGENTS.md`, so the execution plan must resolve that drift before editing.

## Risk Profile

Medium-high. The risk is not algorithmic complexity; it is lifecycle coupling. Driver paths also own artifacts, baseline checks, failure persistence, retry counters, sleep behavior, and final status. A too-broad helper could hide important differences between `run_once`, `run_loop`, and focused migration mode.

## Validation

- `uv run pytest tests/test_loop_migration_tick.py`
- `uv run pytest tests/test_focus_on_live_migrations.py tests/test_scope_loop_integration.py tests/test_run.py`
- `uv run pytest`

## Fit With Taste

This fits the taste only if the planner wants to pay down `loop.py` control-flow debt now. It should be rejected if the target migration is meant to stay tightly scoped to migration tick tests, because the broader boundary cleanup risks mixing multiple rationales.
