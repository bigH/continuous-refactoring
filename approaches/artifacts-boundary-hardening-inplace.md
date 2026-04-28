# Approach: In-Place Artifact Boundary Hardening

## Strategy
- Keep module surfaces stable and refactor inside the existing cluster with minimal churn:
  - `src/continuous_refactoring/artifacts.py`
  - `src/continuous_refactoring/agent.py`
  - `src/continuous_refactoring/loop.py`
  - `src/continuous_refactoring/phases.py`
  - `src/continuous_refactoring/migration_tick.py`
  - `src/continuous_refactoring/routing_pipeline.py`
  - `src/continuous_refactoring/config.py`
  - `src/continuous_refactoring/git.py`
  - `src/continuous_refactoring/cli.py`
- Treat `artifacts.py` as the current error and telemetry spine, but harden it so every external effect returns actionable causes and preserves `__cause__`.
- At module boundaries (agent, cli, loop, phases, routing, migration, git, config) translate only where behavior needs a boundary contract change:
  - Keep original exceptions as nested causes unless caller-level signal is improved by context.
  - Avoid blanket wrapping inside helper functions that are already at the callsite.

## Tradeoffs
- Lowest blast radius and easiest to apply under an active migration.
- No new module-level indirection and little `__init__.py` risk.
- Best fit for taste version 1: strong boundary comments only where contract changes.
- Leaves `artifacts.py` still carrying multiple concerns (capture/state/path/root metadata), but no risky cut needed for this migration.
- Keeps direct import compatibility with `ContinuousRefactoringError` and existing `_SUBMODULES`.

## Estimated phases
1. Add migration tests for failure-cause retention
2. Introduce explicit boundary helpers and nested exceptions in `artifacts.py`
3. Update cluster modules to catch and wrap only at decision points
4. Add regression tests on loop/migration-path behavior
5. Tighten CLI exit messaging while preserving exact user-visible strings that tests assert

### Phase intent
- Phase 1: Add focused tests in `tests/test_continuous_refactoring.py`, `tests/test_phases.py`, `tests/test_loop_migration_tick.py`, `tests/test_routing.py` for `__cause__` preservation.
- Phase 2: In `artifacts.py`, add small helpers for atomic JSON/log writes and command capture parsing that include nested underlying errors.
- Phase 3: In cluster modules, avoid new broad wrappers; replace ambiguous messages with boundary-specific context where needed.
- Phase 4: Verify migration and loop flow still emits expected artifacts summaries and commit handoff semantics.
- Phase 5: Run targeted migration tests, then run full suite as final gate.

## Risk profile
- Technical risk: low to medium
- Blast radius: medium, because changes touch loop routing and failure persistence paths
- Failure modes:
  - Message-level test regressions if we over-wrap and lose exact strings.
  - Slightly more verbose failure paths in `artifacts.py` impacting readability if too many wrappers are added.
  - No new APIs expected, so integration regression risk stays low.

## Why this first
- It satisfies the taste mandate (boundary-aware wrapping with cause chaining) without a disruptive module split.
- It keeps compatibility and can be evaluated quickly with tight, deterministic phase gates.
