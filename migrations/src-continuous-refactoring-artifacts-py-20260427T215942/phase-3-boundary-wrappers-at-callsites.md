# Phase 3: Boundary wrappers at module seams

## Objective
Apply boundary wrappers at adjacent module seams, preserving causes while keeping existing callsite semantics stable.

## Scope
- `src/continuous_refactoring/agent.py`
- `src/continuous_refactoring/git.py`
- `src/continuous_refactoring/phases.py`
- `tests/test_run.py`
- `tests/test_routing.py`
- `tests/test_loop_migration_tick.py`
- `tests/test_phases.py`

## Instructions
1. In `agent.py`, wrap subprocess/process-launch failures with `ContinuousRefactorError` when a module boundary message improves troubleshooting, and preserve the original exception via `from`.
2. In `git.py`, keep `GitCommandError` as a boundary type and add nested causes consistently where subprocess launch/runtime failures are converted into module boundary errors.
3. In `phases.py`, preserve verdict flow while making readiness and phase-result errors boundary-safe at decision points.
4. Keep semantics that callers depend on:
   - stable control flow
   - stable exception class behavior
   - stable user-visible strings unless a wrapped-context test justifies a targeted delta.
5. Add/adjust tests:
   - `tests/test_run.py` for module-seam command-boundary cause retention.
   - `tests/test_routing.py` for routing/decision stability under wrapped failures.
   - `tests/test_loop_migration_tick.py` to ensure event summaries still include meaningful root-cause context.

## Precondition
- Phase 2 complete and green.
- `tests/test_continuous_refactoring.py`, `tests/test_loop_migration_tick.py`, and `tests/test_routing.py` pass with phase-2 contracts in place.
- `tests/test_phases.py` is green before this phase.
- No edits are made in `config.py`, `loop.py`, or `cli.py` during this phase.

## Definition of Done
- `agent.py`, `git.py`, and `phases.py` boundary wrappers preserve `__cause__` and keep current call patterns intact.
- No new external API is introduced.
- Behavior for run/routing remains unchanged in flow and decision results while asserting cause retention where wrapped.
- No test in phase scope is left failing.

## Validation steps
- `uv run pytest tests/test_run.py`
- `uv run pytest tests/test_routing.py`
- `uv run pytest tests/test_loop_migration_tick.py tests/test_phases.py`
