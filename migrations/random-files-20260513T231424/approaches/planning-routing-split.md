# Planning Routing Split

## Strategy
Refactor `routing_pipeline.py` into tighter domain-focused units around three flows: planning tick orchestration, scope/classification routing, and planning-step execution reporting. Keep public exports stable while reducing deeply interleaved control flow.

## Why this path
- Largest readability gain in the heaviest orchestration file in scope.
- Better supports future migration behavior work without touching `loop.py` structure.
- Keeps FQNs meaningful and avoids speculative interfaces.

## Tradeoffs
- Pros: cleaner flow boundaries, easier testing of route decisions, less cognitive load.
- Cons: medium migration risk from moving logic in orchestration hot path.

## Estimated phases
1. Extract pure routing helpers (`routing_pipeline.py`)
- Goal: isolate pure decision functions (outcome mapping, summary composition, failure-kind mapping).
- Required effort: `low`
- Risk: low

2. Extract planning execution coordinator
- Goal: move planning-step run + artifact-path error packaging into a dedicated module (e.g., `planning_routing.py`) while preserving `route_and_run` behavior.
- Required effort: `high`
- Risk: medium-high

3. Collapse callsite complexity
- Goal: simplify `route_and_run` into ordered high-level steps with explicit boundary error translation.
- Required effort: `medium`
- Risk: medium

4. Route-behavior regression tests
- Goal: assert `commit/blocked/abandon/not-routed` invariants, including `planning.review-2` failure mapping.
- Required effort: `medium`
- Risk: low

## Risk profile
- Overall risk: **medium**.
- Primary risks: route outcome regressions, subtle artifact-path mismatch on planning failures.
- Mitigations: snapshot assertions for route decisions; preserve call-role and failure-kind strings.

## Best fit when
You want structural clarity now and are willing to accept moderate orchestration refactor risk.
