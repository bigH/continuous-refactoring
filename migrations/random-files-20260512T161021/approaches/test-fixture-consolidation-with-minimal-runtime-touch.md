# Approach: Test Fixture Consolidation, Minimal Runtime Touch

## Strategy
Refactor duplicated test scaffolding first across the selected test files, then make minimal runtime code adjustments required by clearer tests. Use tests as the primary design pressure and avoid broad production reshaping.

## Why this approach
- Fastest path to readability and maintainability in this random-files batch.
- Low interface risk because runtime changes are intentionally narrow.
- Aligns with taste: small abstractions, readable flow, outcome-based tests.

## Tradeoffs
- Pros: immediate reduction in test duplication and cognitive load; safer incremental commits.
- Cons: may miss deeper architectural simplifications in runtime modules.

## Estimated phases

### Phase 1: Consolidate repeated test setup patterns
- Scope: shared helpers in `tests/test_taste_refine.py`, `tests/test_loop_migration_tick.py`, `tests/test_phases.py`, `tests/test_planning_publish.py`.
- Deliverable: fewer bespoke helpers, clearer intent per test.
- required_effort: `low`
- Risk: low

### Phase 2: Adjust runtime seams only where tests expose ambiguity
- Scope: `git.py`, `phases.py`, planning publish seams touched by improved tests.
- Deliverable: narrower, more explicit behavior without contract changes.
- required_effort: `medium`
- Risk: medium

### Phase 3: Harden assertions around outcomes and side effects
- Scope: replace call-shape assertions with state/output assertions where practical.
- Deliverable: more robust tests with less implementation coupling.
- required_effort: `low`
- Risk: low

### Phase 4: Remove dead or redundant paths revealed by cleanup
- Scope: test-only dead branches and any now-unused tiny runtime fallback.
- Deliverable: smaller code surface and fewer misleading branches.
- required_effort: `low`
- Risk: low

## Risk profile
Overall risk: **Low to Medium**.
Greatest risk is under-addressing root runtime complexity by staying test-first. Mitigation: require at least one runtime simplification pass after fixture consolidation, and reject no-op “test-only” cleanup if runtime duplication remains obvious.
