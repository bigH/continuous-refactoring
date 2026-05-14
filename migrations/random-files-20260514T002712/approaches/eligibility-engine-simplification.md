# Approach: Eligibility Engine Simplification

## Strategy
Focus directly on candidate discovery and eligibility logic as one cohesive “eligibility engine.” Consolidate duplicate checks and naming drift in `migration_tick.py`/`migrations.py`, while preserving existing contract behavior through targeted regression tests.

## Why this approach
- Highest payoff for readability in active runtime logic.
- Reduces repeated status/phase/cooldown predicates.
- Improves future migration scheduling changes by centralizing intent.

## Tradeoffs
- Higher chance of behavioral regression if equivalence coverage misses a branch.
- Requires careful sequencing to avoid accidental interface change.
- Less immediate value to planning-publish edge cases.

## Estimated Phases

### Phase 1: Characterization tests for eligibility matrix
- Scope: tests around `enumerate_eligible_manifests`, planning candidate selection, cooldown + effort override interactions.
- Work: add matrix-style outcome tests (status, cooldown, effort budget, human-review flag).
- required_effort: `medium`
- Risk: Medium.

### Phase 2: Consolidate eligibility predicates
- Scope: `src/continuous_refactoring/migration_tick.py`, optional small helper exposure in `src/continuous_refactoring/migrations.py`.
- Work: unify predicate logic, remove duplication, keep identical observable outcomes.
- required_effort: `high`
- Risk: High (core scheduler behavior).

### Phase 3: Boundary error-translation pass
- Scope: `src/continuous_refactoring/migrations.py`.
- Work: confirm boundary-only error translation remains consistent and explicit after refactor.
- required_effort: `low`
- Risk: Low.

## Risk Profile
- Overall risk: Medium to High.
- Primary failure mode: changed candidate ordering/selection in mixed migration sets.
- Mitigation: characterization tests first; preserve ordering contract (`created_at` sort) explicitly.

## Rollback posture
- If Phase 2 destabilizes behavior, revert Phase 2 and keep Phase 1 tests as regression harness for future attempts.
