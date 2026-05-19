# Phase 1: Map Exception Boundaries

## Scope
- `src/continuous_refactoring/git.py`
- `src/continuous_refactoring/phases.py`
- `src/continuous_refactoring/planning_publish.py`
- Existing failure-path assertions in:
  - `tests/test_git.py`
  - `tests/test_phases.py`
  - `tests/test_planning_publish.py`

## Goals
1. Build a concrete inventory of where each module translates exceptions at boundaries.
2. Identify inconsistent message patterns and any places where `raise ... from exc` is missing.
3. Identify any intra-module over-wrapping that should not survive into implementation phases.

## Precondition
- No active phase remains incomplete before this phase in the migration sequence.
- The expected source and test files listed in Scope exist at their current paths.
- Migration status remains `ready`/in-progress for this migration, the human-review gate is cleared, and the phase is selected as the current execution target.

## Implementation Instructions
1. Read each scoped source module and list every boundary function that converts lower-level exceptions into `ContinuousRefactorError` or equivalent boundary error types.
2. For each conversion site, capture:
   - function name,
   - source exception classes,
   - translated message anchor,
   - whether `__cause__` is preserved.
3. Cross-check existing tests for each boundary path and note what is already asserted vs. missing.
4. Record the inventory in this phase file under an added section `## Boundary Inventory` (concise bullets), without changing runtime code yet.
5. If the inventory shows a necessary CLI behavior, XDG state, repo-written file, migration manifest structure, public exception type, or top-level message-anchor change, stop and surface that exact old/new interface behavior for human review before implementation.

## Validation Steps
1. Confirm inventory references only real call paths and symbols currently present in scope.
2. Run targeted tests to ensure no behavior changes were introduced while documenting:
   - `uv run pytest tests/test_git.py tests/test_phases.py tests/test_planning_publish.py`
3. Run full validation command:
   - `uv run pytest`

## Definition of Done
- `## Boundary Inventory` exists in this phase file and lists all boundary translation sites in scoped modules.
- Each listed site includes whether cause chaining is preserved.
- Candidate inconsistencies and over-wrapping sites are explicitly identified for Phase 2.
- No runtime behavior changes were made in this phase.
- Full validation command `uv run pytest` passes.

## Boundary Inventory
- `src/continuous_refactoring/git.py`
  - `run_command`: converts `OSError` -> `GitCommandError` with anchor `command could not be started: ...` and preserves cause (`raise ... from exc`).
  - `run_command`: converts `subprocess.CalledProcessError` -> `GitCommandError` with anchor `command failed (...)` and preserves cause (`raise ... from exc`).
  - `require_clean_worktree`: raises `ContinuousRefactorError` directly with anchor `Aborting: working copy has local changes...`; no lower-level exception input/cause chain.
  - `current_branch`: raises `ContinuousRefactorError` directly with anchor `Cannot determine current git branch...`; no lower-level exception input/cause chain.
  - `git_commit`: raises `ContinuousRefactorError` directly with anchor `No changes to commit.`; no lower-level exception input/cause chain.

- `src/continuous_refactoring/phases.py`
  - `check_phase_ready`: converts non-zero agent exit into `ContinuousRefactorError` with anchor `Phase ready-check agent failed with exit code ...` and preserves cause (`subprocess.CalledProcessError` via `raise ... from process_error`).
  - `check_phase_ready`: helper `_parse_ready_verdict` raises direct `ContinuousRefactorError` anchors (`Phase ready-check produced no output`, `...unrecognised output...`); no lower-level exception input/cause chain.
  - `execute_phase` path: most boundary failures are normalized by `_terminal_phase_failure` into `ExecutePhaseOutcome(status="failed")` rather than re-raising exceptions; this is a structured boundary translation with no `__cause__` propagation surface.

- `src/continuous_refactoring/planning_publish.py`
  - `publish_planning_workspace`: converts unexpected release-lock cleanup failure into `ContinuousRefactorError` with composite message and preserves cause (`raise ... from error`).
  - `_prepare_transaction_paths`: converts `OSError` -> `ContinuousRefactorError` (`Could not create planning transaction directory ...`) with cause preserved.
  - `_acquire_publish_lock`: converts `OSError` -> `ContinuousRefactorError` for lock create/write failures (`Could not acquire...`, `Could not write...`) with cause preserved.
  - `_repo_relative`: converts `ValueError` -> `ContinuousRefactorError` (`Live migration path must stay inside repository: ...`) with cause preserved.
  - `_dirty_live_migration_paths`: boundary failure is direct `ContinuousRefactorError` on non-zero git status command (`Could not inspect live migration git status...`); no chained lower-level exception object is kept.
  - `snapshot_tree_digest`: converts file-system `OSError` at stat/read boundaries into `ContinuousRefactorError` (`Could not stat snapshot path...`, `Could not read snapshot path...`) with cause preserved.
  - `publish_planning_workspace` / `_publish_planning_workspace_locked` / `_publish_staged_snapshot`: many boundary failures are translated to `PlanningPublishError` via `_raise_result(...)` carrying structured `PlanningPublishResult` instead of nested exception chaining.

- Cross-check against existing failure-path tests
  - `tests/test_git.py`: covers both `run_command` wrapped paths and explicitly asserts `__cause__` for `CalledProcessError` and `FileNotFoundError`; does not assert direct-message anchors for `require_clean_worktree`/`current_branch`.
  - `tests/test_phases.py`: covers `check_phase_ready` boundary parse errors and non-zero exit wrapping with preserved `CalledProcessError` cause; exercises structured failure outcomes for execute/validation loops.
  - `tests/test_planning_publish.py`: heavily covers blocked/failed `PlanningPublishError` result surfaces and transaction rollback behavior; coverage is outcome-centric and mostly does not assert chained `__cause__` for lower-level `ContinuousRefactorError` conversion sites.

- Candidate inconsistencies and over-wrapping targets for Phase 2
  - Inconsistent boundary shape across scoped modules: some paths expose nested exception chaining (`raise ... from ...`), while others convert to structured result errors (`PlanningPublishError`/`ExecutePhaseOutcome`) without `__cause__` surface. Phase 2 should normalize where this asymmetry is accidental.
  - `phases.py` has mixed boundary channels inside one module (exception raising in `check_phase_ready` vs structured failure returns in execution path). Phase 2 should ensure message-anchor and failure-kind consistency across these channels.
  - `planning_publish.py` currently translates many expected control-flow failures via `_raise_result(...)`; verify in Phase 2 that no intra-module re-wraps add redundant message layers where bubbling existing `PlanningPublishError` already preserves full signal.
