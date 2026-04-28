# Phase 3: Helper Tightening And Deletion

## Objective
Clean up helper naming and delete redundant stage glue left behind by the pipeline extraction without changing planning behavior.

## Scope
- `src/continuous_refactoring/planning.py`
- `tests/test_planning.py`
- `AGENTS.md` only if a planning-specific load-bearing subtlety statement becomes stale because of this cleanup

## Instructions
1. Tighten helper names so they describe real responsibilities such as context assembly, plan reload, or manifest refresh.
2. Delete dead locals, duplicated branches, or transitional helpers that became unnecessary after Phase 2.
3. Keep parsing and phase discovery local unless a tiny boundary cleanup falls out naturally from the Phase 2 structure.
4. If this cleanup changes which planning implementation detail `AGENTS.md` points at, update the relevant planning subtlety note in the same phase. Do not add noise.
5. Re-run the strongest repo-sanctioned validation after the local planning tests pass.

## Precondition
- Phase 2 is complete and `run_planning()` already uses the explicit stage pipeline introduced there.
- The repository is green on full `uv run pytest` after the Phase 2 refactor.
- The only remaining planned work is semantics-preserving cleanup inside the existing `planning.py` pipeline shape, not another control-flow rewrite or contract change.

## Definition of Done
- Redundant locals, helper paths, or duplicated orchestration code introduced or left exposed by earlier phases are deleted.
- Remaining helper names in `planning.py` are tighter and more truthful about what they read or refresh.
- `tests/test_planning.py` still passes with the same behavioral assertions covering stage order, context reload, revise/review-2 flow, and manifest refresh timing.
- `AGENTS.md` is updated in the same phase if and only if one of its planning-specific invariants would otherwise become stale.
- Full `uv run pytest` passes.
- The repository remains shippable.

## Validation
- Optional focused check while iterating: `uv run pytest tests/test_planning.py`
- Required phase gate: `uv run pytest`
