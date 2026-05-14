# Phase 2: Normalize Boundary Wrapping

required_effort: medium
effort_reason: Multiple module-boundary paths must be aligned without changing public contracts.

## Scope
- `src/continuous_refactoring/git.py`
- `src/continuous_refactoring/phases.py`
- `src/continuous_refactoring/planning_publish.py`

## Goals
1. Standardize exception translation at module boundaries.
2. Preserve nested causes with `raise ... from exc` at every boundary conversion.
3. Remove unnecessary intra-module re-wrapping while preserving current external behavior and compatibility-sensitive message anchors.

## Precondition
- Phase 1 is complete and its boundary inventory is available in `phase-1-map-exception-boundaries.md`.
- Boundary functions and symbols identified in Phase 1 still exist or have equivalent direct successors.
- No unreviewed interface-contract change has been introduced for CLI flags, XDG state, or migration manifest structure.

## Implementation Instructions
1. For each boundary site from Phase 1, ensure translation happens exactly once at the correct module boundary.
2. Convert missing boundary chains to explicit exception nesting (`raise ... from exc`) so original failure context remains inspectable.
3. Normalize message phrasing to consistent anchors where tests and callers rely on semantic wording.
4. Delete dead or duplicate boundary branches discovered during normalization when safe.
5. Keep abstractions minimal and local; avoid introducing speculative interfaces.

## Validation Steps
1. Run focused tests for changed behavior paths:
   - `uv run pytest tests/test_git.py tests/test_phases.py tests/test_planning_publish.py`
2. Run full validation command:
   - `uv run pytest`

## Definition of Done
- Scoped modules use consistent boundary translation patterns.
- Boundary conversions preserve `__cause__` consistently where wrapping occurs.
- Intra-module over-wrapping identified in Phase 1 is removed or explicitly justified in code shape.
- No intended change to CLI/XDG/manifest contracts is introduced.
- Full validation command `uv run pytest` passes.
