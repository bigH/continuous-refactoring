# Approach: attempt-flow-state

## Strategy
Refactor the retry/attempt lifecycle in `loop.py` into a small internal state model while keeping current public behavior and CLI contract unchanged. The goal is to reduce the nested retry/route branches and make outcomes explicit (`success`, `failed`, `skipped`, `migration`) with one exit path.

This is a local-cluster cleanup anchored in `loop.py` only, plus minimal `__init__.py` export updates if needed for renamed helpers.

## Why this fits
The current `_route_and_run` + in-loop retry logic is hard to read and easy to mis-handle when adding new failure modes. A small explicit state shape reduces branching complexity without introducing speculative architecture.

## Tradeoffs
1. Pros
   - Better local comprehensibility and future maintainability in the hottest control path.
   - Fewer accidental differences between `run_once` and `run_loop` by sharing attempt execution helpers.
   - Better surface for tests and invariants (attempt state transitions become explicit).
2. Cons
   - This file is behavioral core; even small structural refactors carry merge risk.
   - Requires careful parity pass to avoid changing metrics side effects (`RunArtifacts` counters/events).
   - Could be perceived as over-abstraction if split too fine.

## Estimated phases
1. Phase 1 — behavior map
   - Derive exact transition table for retry outcomes and final statuses from existing tests.
   - Add property tests or table-driven unit tests for attempt transitions if practical.
2. Phase 2 — state model + executor
   - Introduce internal `AttemptState` and `execute_refactor_attempt` helper.
   - Move branch-heavy blocks out of both `run_once` and `run_loop`, while preserving artifact writes and commit/push behavior.
3. Phase 3 — parity lock
   - Run focused e2e and planning-migration tests; ensure counters and status strings remain unchanged for the tested paths.

## Risk profile
- Risk level: medium-high.
- Operational risk: medium-high because it touches branching semantics around agent execution, rollback, and commit finalize.
- Acceptance condition: strict parity on targeted regression scenarios before broadening scope.

