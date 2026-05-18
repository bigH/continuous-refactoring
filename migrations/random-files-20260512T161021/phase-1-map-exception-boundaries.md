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
