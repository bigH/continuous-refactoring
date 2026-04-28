# Phase 3: Boundary wrappers at module seams

## Objective
Apply boundary wrappers at adjacent module seams, preserving causes while keeping existing callsite semantics stable across routing and migration-tick flows.

## Scope
- `src/continuous_refactoring/agent.py`
- `src/continuous_refactoring/git.py`
- `src/continuous_refactoring/migration_tick.py`
- `src/continuous_refactoring/phases.py`
- `tests/test_run.py`
- `tests/test_routing.py`
- `tests/test_loop_migration_tick.py`
- `tests/test_phases.py`

## Instructions
1. In `agent.py`, wrap subprocess/process-launch failures with `ContinuousRefactorError` when a module boundary message improves troubleshooting, and preserve the original exception via `from`.
2. In `git.py`, keep `GitCommandError` as a boundary type and add nested causes consistently where subprocess launch/runtime failures are converted into module boundary errors.
3. In `phases.py`, preserve verdict flow while making readiness and phase-result errors boundary-safe at decision points.
4. In `migration_tick.py`, preserve defer/blocked/abandon decision flow while keeping ready-check and phase-result failures tied to meaningful summaries and original causes.
5. Keep semantics that callers depend on:
   - stable control flow
   - stable exception class behavior
   - stable user-visible strings unless a wrapped-context test justifies a targeted delta.
6. Add/adjust tests:
   - `tests/test_run.py` for module-seam command-boundary cause retention.
   - `tests/test_routing.py` for routing/decision stability under wrapped failures.
   - `tests/test_loop_migration_tick.py` to ensure migration-tick summaries still include meaningful root-cause context.

## Precondition
- Phase 2 is marked complete in the migration manifest.
- Phase-2 boundary contracts are present in `artifacts.py` and their tests.
- No edits are made in `config.py`, `loop.py`, or `cli.py` during this phase.

## Definition of Done
- `agent.py`, `git.py`, `phases.py`, and `migration_tick.py` boundary wrappers preserve `__cause__` and keep current call patterns intact.
- No new external API is introduced.
- Behavior for run/routing/migration tick remains unchanged in flow and decision results while asserting cause retention where wrapped.
- No test in phase scope is left failing.

## Validation steps
- `uv run pytest tests/test_run.py`
- `uv run pytest tests/test_routing.py`
- `uv run pytest tests/test_loop_migration_tick.py tests/test_phases.py`
