# Phase Execution State Machine Tightening

## Strategy
Make `phases.py` execution paths more explicit as a state machine: ready-check, agent execution, validation, rollback/finalize. Reduce branch entanglement and make terminal outcomes (`done`, `awaiting_human_review`, `failed`) mechanically obvious.

## Why this path
- `phases.py` contains load-bearing behavior (validation gate, retries, rollback semantics).
- Explicit state transitions improve maintainability and failure diagnosis.
- Preserves existing external contracts while hardening internals.

## Tradeoffs
- Pros: clearer retry semantics, easier future changes to phase completion logic.
- Cons: higher risk because rollback/commit behavior is sensitive and easy to regress.

## Estimated phases
1. Name and isolate transition handlers
- Goal: split major execution transitions into focused helpers with strict typed outcomes.
- Required effort: `medium`
- Risk: medium

2. Normalize rollback/failure funnels
- Goal: ensure all terminal failures pass through one boundary that logs, reverts, and annotates `failure_kind` consistently.
- Required effort: `high`
- Risk: high

3. Validation-result contract tightening
- Goal: make validation pass/fail/infra-failure mapping exhaustive and test-covered.
- Required effort: `medium`
- Risk: medium

4. Behavior-preserving test reinforcement
- Goal: expand tests around retry budgets, head reset behavior, and final status reasons.
- Required effort: `high`
- Risk: medium

## Risk profile
- Overall risk: **medium-high**.
- Primary risks: subtle commit/revert regressions and status misclassification.
- Mitigations: explicit transition table assertions; verify unchanged user-visible behavior.

## Best fit when
You need deeper correctness confidence in phase execution and can afford heavier validation work.
