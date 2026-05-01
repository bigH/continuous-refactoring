# Approach: In-Place Domain Seams

## Strategy
- Keep `src/continuous_refactoring/migrations.py` as the public home for migration helpers and refactor internally for clearer sections:
  - manifest value types and status constants,
  - phase cursor helpers,
  - manifest persistence,
  - wake-up eligibility.
- Tighten helper naming so call sites read in domain terms instead of implementation terms.
- Grow tests around the current public functions before moving code around.
- Preserve import paths everywhere else. No package-surface churn, no new module.

## Tradeoffs
- Safest option. Lowest merge pain and lowest risk to `loop.py`, `planning.py`, `phases.py`, and `migration_tick.py`.
- Good fit if the real problem is readability and local change friction, not the file count.
- Leaves one module owning multiple concerns. Cleaner, yes; simpler architecture, not really.
- Misses the chance to make codec and persistence boundaries more explicit.

## Estimated phases
1. Add characterization tests for phase lookup, cursor advance, completion, load/save failures, and wake-up eligibility.
   - `required_effort`: `low`
2. Refactor private helpers so lookup, cursor, and eligibility logic read top-down and duplication around phase resolution disappears.
   - `required_effort`: `low`
3. Isolate manifest save/load flow into tighter private helpers inside `migrations.py`, keeping boundary wrapping only at filesystem and JSON edges.
   - `required_effort`: `low`
4. Trim stale helper shapes and rerun targeted plus broad pytest coverage.
   - `required_effort`: `low`

## Risk profile
- Technical risk: low
- Blast radius: low
- Failure modes:
  - Cleanup accidentally changes exact error strings that tests or callers rely on.
  - Helper reshuffling obscures the current codec boundary instead of clarifying it.

## Best when
- We want the fastest safe win.
- We are not yet confident a new module boundary will pay for itself.
