# Approach: Minimal Safe Cleanup

## Strategy
Do the smallest useful refactor in scoped files: remove obvious local complexity, improve naming, and keep behavior unchanged. Avoid broader structural moves; optimize for low risk and quick mergeability.

## Why this approach
- Fastest path with least blast radius.
- Fits low default effort runs and frequent incremental migration ticks.
- Good when confidence or bandwidth is limited.

## Tradeoffs
- Leaves deeper structural debt in place.
- Lower long-term payoff than eligibility-engine consolidation.
- May require multiple follow-up migrations.

## Estimated Phases

### Phase 1: Micro-cleanups with no behavior change
- Scope: `src/continuous_refactoring/migrations.py`, `src/continuous_refactoring/migration_tick.py`.
- Work: naming clarity, tiny helper extraction, dead-branch trimming when clearly redundant.
- required_effort: `low`
- Risk: Low.

### Phase 2: Targeted regression assertions
- Scope: `tests/test_prompts.py`, `tests/test_planning_publish.py`, plus any directly impacted tests.
- Work: tighten assertions only where cleanups changed expression but not behavior.
- required_effort: `low`
- Risk: Low.

## Risk Profile
- Overall risk: Low.
- Primary failure mode: too-conservative scope yields minimal improvement.
- Mitigation: explicitly call out deferred cleanups for next migration.

## Rollback posture
- Straightforward single-commit revert path; almost no coupling across modules.
