# Approach: loop-attempt-state-machine

## Strategy
Extract the two execution paths (`run_once` and `run_loop`) into a shared, explicit attempt-state machine while keeping migration routing, retry semantics, and artifact logging intact.

Create a tiny immutable execution state in `loop.py` that owns:
- target selection/fallback
- baseline/migration preconditions
- attempt execution loop
- final status transitions (`running`, `completed`, `agent_failed`, `validation_failed`, `migration_failed`, `max_consecutive_failures`, etc.)

Then drive both `run_once` and `run_loop` through that shared engine with strict module-local boundaries.

## Why this approach fits the migration
Current `run_once` and `run_loop` duplicate high-level flow (`prepare branch -> route -> prompt -> run agent -> run tests -> commit`), which is already a candidate for cohesion cleanup. A shared state machine reduces duplication and makes failure transitions explicit without changing semantics.

## Tradeoffs
1. Pros: lower long-term maintenance for new run modes and easier invariant testing around max-attempts/consecutive-failure transitions.
2. Pros: cleaner `run_once` shape for CLI and future migration behavior.
3. Cons: medium refactor depth with visible churn across `loop.py` and more unit test fixtures.
4. Cons: highest risk among options because it touches retry ordering, artifact event recording, and branch lifecycle in one place.

## Estimated phases
1. Define a compact run-state model and state transition table in `loop.py`.
2. Move target resolution/fallback and max-attempt normalization into shared prelude helpers.
3. Implement shared attempt runner used by both `run_once` and `run_loop`.
4. Keep `_route_and_run` behavior unchanged and adapt it as a terminal step in the state machine.
5. Strengthen tests where event ordering and status transitions are asserted.

## Validation
1. `uv run pytest tests/test_run_once.py tests/test_run_once_regression.py tests/test_run.py`
2. `uv run pytest tests/test_loop_migration_tick.py tests/test_scope_loop_integration.py`
3. `uv run pytest tests/test_targeting.py tests/test_scope_expansion.py`
4. Add focused property-based tests for state transitions around unlimited attempts (`max_attempts=0`) and consecutive-failure cutoff.

## Risk profile
- Risk level: medium-high.
- Primary technical risk is accidental change in retry/branch behavior under corner cases.
- Requires stronger invariant tests before merge and broad rerun of loop-focused suites.
