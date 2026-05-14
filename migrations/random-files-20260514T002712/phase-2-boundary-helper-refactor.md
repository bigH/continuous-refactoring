# Phase 2: Boundary Helper Refactor

required_effort: medium
effort_reason: Scheduler/eligibility sequencing is easy to regress without careful equivalence checks.

## Goal
Simplify and clarify boundary helper decomposition and call flow in migration boundary modules while preserving established contracts.

## Scope
- `src/continuous_refactoring/migrations.py`
- `src/continuous_refactoring/migration_tick.py`
- Minimal related tests updated only when needed to reflect clearer-but-equivalent behavior expression

## Out of Scope
- Changing CLI flags, parser behavior, or command routing semantics
- Changing migration manifest JSON contract or file layout semantics
- Broad structural `loop.py` redesign

## Precondition
- Phase 1 is complete and its contract tests are present in the branch.
- The target helper/function entry points to be refactored still match the contracts locked in Phase 1.
- No newly introduced migration-interface contract change is pending unresolved human review for this migration.

## Implementation Instructions
1. Refactor in small, reviewable slices:
   - tighten helper boundaries around visible-candidate enumeration;
   - simplify preflight/consistency flow control in tick paths;
   - remove redundant or dead conditional branches where covered by boundary tests.
2. Preserve boundary error translation strategy:
   - keep translation/wrapping at module boundaries;
   - do not add deep internal translation layers that hide signal.
3. Keep domain-focused naming and FQNs meaningful; avoid mechanical module reshaping.
4. If a proposed simplification changes observed behavior, either:
   - reject it in this phase, or
   - explicitly convert it into a surfaced interface change and stop for human review.

## Validation Steps
1. Run focused tests around migrations/tick behavior after each logical refactor slice.
2. Run `uv run pytest` before phase completion.
3. Manually inspect key changed call sites for preserved ordering/selection semantics where tests are intentionally broad.

## Definition of Done
- Boundary helper and flow code is materially simpler (clearer decomposition and fewer redundant branches) without changing locked boundary behavior.
- Contract tests from Phase 1 remain green without weakening assertions.
- No unintended interface drift in migration visibility, eligibility gating, or boundary error surfacing.
- `uv run pytest` passes.
