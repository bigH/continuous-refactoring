# Approach: Error Taxonomy with Boundary-Specific Types

## Strategy
- Introduce a dedicated error module and explicit boundary error classes while preserving public compatibility:
  - Add `src/continuous_refactoring/errors.py` with `ContinuousRefactoringError` as canonical base.
  - Re-export `ContinuousRefactoringError` from `artifacts.py` to keep existing imports and `__init__` behavior intact.
  - Add module-level boundary types: `CommandBoundaryError`, `ArtifactBoundaryError`, `GitBoundaryError`, `MigrationBoundaryError`, `LoopBoundaryError`.
- Move wrapping logic so each cluster module becomes explicit about what it owns and what it reports:
  - `agent` and `config` wrap infra faults when translating to domain failure outcomes.
  - `loop`, `phases`, `migration_tick`, and `routing_pipeline` wrap only policy-level failures.
- Keep semantics of CLI and migration scheduling unchanged; preserve existing command strings, artifact path names, and summary structure.

## Tradeoffs
- Clearer operational signal and cleaner root-cause triage.
- Stronger alignment with taste instruction on nested exceptions at boundaries.
- Larger import churn across the cluster and tests.
- Must update `continuous_refactoring.__all__` import graph after moving exported error ownership, which is extra mechanical risk.
- Potentially over-specified errors if boundary classes expand faster than actual domain needs.

## Estimated phases
1. Add `errors.py` and compatibility export path
2. Create boundary exception types and migrate `artifacts.py` to consume canonical base
3. Shift catch/raise behavior in `agent.py`, `git.py`, `loop.py`, `phases.py`, `migration_tick.py`, `routing_pipeline.py`
4. Update `cli.py` and tests that assert exact exception types/messages
5. Run targeted migration and full project verification

### Phase intent
- Phase 1: New module only, no production behavior changes yet.
- Phase 2: Add wrappers and nesting around I/O/process/git/agent callouts.
- Phase 3: Convert consumer catches to boundary-aware failures and update decision records where needed.
- Phase 4: Add/adjust tests for exception typing, compatibility of imports, and boundary names in messages.
- Phase 5: Validate `tests/test_continuous_refactoring.py`, `tests/test_run.py`, `tests/test_run_once.py`, `tests/test_phases.py`, and `tests/test_loop_migration_tick.py`.

## Risk profile
- Technical risk: medium
- Blast radius: medium
- Failure modes:
  - Import graph breakage from moved exported symbols into `__init__.py` and `_SUBMODULES`.
  - Tests that assert specific exception text may break on message wrapping style.
  - Additional migration complexity from adding new module and maintaining alias compatibility.

## Why choose this if stability budget allows
- Better long-term maintainability and explicit domain boundaries.
- Clear runway for future non-trivial refactors where cross-module ownership gets noisier than today.
