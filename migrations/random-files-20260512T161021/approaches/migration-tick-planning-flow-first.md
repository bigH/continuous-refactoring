# Approach: Migration Tick + Planning Flow First

## Strategy
Prioritize planning/tick correctness and scheduling semantics, then fold adjacent fixes in phase execution and publish tests. Drive around `tests/test_loop_migration_tick.py` as the anchor, with strict protection of planning-state and human-review gates.

## Why this approach
- Best when recent failures cluster around migration selection/execution order.
- Reduces blast radius by locking orchestration behavior first.
- Fits repo load-bearing subtleties around planning resume and tick deferral.

## Tradeoffs
- Pros: stabilizes highest-coordination code paths early.
- Cons: can defer simpler cleanup in git/phases error handling; more integration-heavy validation.

## Estimated phases

### Phase 1: Build behavior matrix from migration tick tests
- Scope: `tests/test_loop_migration_tick.py` plus related helpers.
- Deliverable: explicit matrix for eligibility, planning-first behavior, cooldown/deferral semantics.
- required_effort: `medium`
- Risk: medium

### Phase 2: Refactor tick/planning logic in small slices
- Scope: scheduling paths only; keep manifest/public schema unchanged.
- Deliverable: simplified routing flow that preserves current user-facing behavior.
- required_effort: `high`
- Risk: high

### Phase 3: Reconcile phase and publish edge tests
- Scope: `tests/test_phases.py`, `tests/test_planning_publish.py` for orchestration-adjacent assertions.
- Deliverable: deterministic tests for ready-check/execute/publish interactions.
- required_effort: `medium`
- Risk: medium

### Phase 4: Verify random-files suite + full pytest
- Scope: target files first, then full gate.
- Deliverable: green targeted suite and no regressions in global run.
- required_effort: `low`
- Risk: low

## Risk profile
Overall risk: **Medium to High**.
Main risk is subtle behavior drift in migration scheduling (planning vs phase execution ordering). Mitigation: phase-gated commits with explicit matrix checks before and after each slice.
