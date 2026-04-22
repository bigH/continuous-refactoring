# Extract Migration Tick

## Strategy

Move migration tick orchestration out of `routing_pipeline.py` into a domain-focused `src/continuous_refactoring/migration_tick.py`. The tick logic is a distinct workflow: enumerate eligible manifests, check readiness, execute a phase, defer or block manifests, and return a routing outcome plus decision record. Today that behavior sits inside routing, which also owns scope expansion, classification, and planning.

The target test can then point at a clearer production boundary. `run_once`, `run_loop`, and the focused migrations loop still call through `routing_pipeline.route_and_run` or `try_migration_tick` during the transition, but the real implementation lives in the new module.

## What Changes

- Create `migration_tick.py` with `try_migration_tick`, `enumerate_eligible_manifests`, and small private helpers for:
  - building phase target labels
  - executing ready phases
  - deferring not-ready phases
  - marking unverifiable phases for human review
  - translating tick errors into `DecisionRecord`
- Keep `routing_pipeline.try_migration_tick` as a direct import or thin delegation only if needed for existing monkeypatch targets, then remove that compatibility layer in the same migration if all call sites and tests can move cleanly.
- Update `tests/test_loop_migration_tick.py` to import or monkeypatch the new module boundary.
- Keep `loop.py` changes minimal: only update imports or call sites if necessary.
- Run the package uniqueness check implicitly through import/tests because new exported symbols can collide via `__init__.py`.

## Estimated Phases

1. Add characterization tests around `try_migration_tick` at the new boundary while preserving current behavior.
2. Extract the tick code and update imports, monkeypatch targets, and `__all__`.
3. Tighten `tests/test_loop_migration_tick.py` so it tests migration tick behavior directly where possible and run-once fallthrough only where the driver boundary matters.
4. Delete any old routing helper or shim that no longer has a caller.

## Tradeoffs

- Clarifies production ownership: routing routes, migration tick ticks.
- Makes future changes to cooldown, human-review, and phase execution less tangled with classifier/planning flow.
- Medium churn across tests because monkeypatch targets currently point through `continuous_refactoring.routing_pipeline`.
- A new module is only worth it if the extraction removes meaningful branching from `routing_pipeline.py`; a tiny wrapper module would be worse than the current state.

## Risk Profile

Medium. Behavior crosses persistence, git state, phase execution, artifacts, and routing outcomes. The highest-risk areas are commit timing around successful phase execution, deferred manifest persistence, and preserving fallthrough to classification when all eligible migrations are not ready.

The stale `AGENTS.md` reference to a missing active `loop.py` migration is a project-doc risk. If this approach edits `loop.py`, the execution plan should either confirm no live `loop.py` migration remains or update `AGENTS.md` in the same commit.

## Validation

- `uv run pytest tests/test_loop_migration_tick.py`
- `uv run pytest tests/test_focus_on_live_migrations.py tests/test_scope_loop_integration.py tests/test_run.py::test_run_phase_ready_check_failure_logs_phase_ready_role tests/test_run.py::test_run_phase_execute_validation_failure_logs_phase_validation_role`
- `uv run pytest tests/test_migrations.py tests/test_phases.py`
- `uv run pytest`

## Fit With Taste

This is the best balance if source clarity matters, not just test cleanup. It creates a domain-focused module with meaningful FQNs and removes routing overload. It should avoid a long-lived compatibility shim unless it is immediately deleted after tests move.
