# Strict Contract Hardening

## Strategy
Strengthen migration consistency guarantees by introducing stricter invariants and more explicit failure surfaces (while preserving current exported API): standardize error translation boundaries, tighten path/phase doc validation, and add richer consistency findings where ambiguity exists.

## Why this approach
- Targets correctness and operability over readability alone.
- Improves diagnostics for migration authors and reduces ambiguous doctor output.
- Good foundation if migration complexity is expected to grow.

## Tradeoffs
- Highest behavior-change risk; may surface new blocking findings in existing migrations.
- Can require coordinated updates to migration docs/manifests in-flight.
- Might trigger more human review due to interface-adjacent behavior shifts.

## Estimated phases
1. Inventory + safety tests around public contracts (`required_effort: medium`)
- Freeze expected outputs for current valid/invalid migration shapes.
- Add tests for boundary error wrapping paths (`OSError`/manifest decode failures).

2. Tighten validation semantics (`required_effort: high`)
- Define and enforce stricter file/path/doc invariants where currently permissive or ambiguous.
- Keep finding taxonomy explicit; add codes only when they capture distinct actionable failures.

3. Improve finding ergonomics (`required_effort: medium`)
- Normalize message style and path targets for human triage quality.
- Ensure severity usage remains consistent with execution gate semantics.

4. Rollout guard + compatibility review (`required_effort: xhigh`)
- Run broad migration corpus checks (including existing live migrations) and document behavior deltas that affect CLI/doctor or execution gating.
- Gate merge on explicit human review of interface impact.

## Risk profile
- Delivery risk: Medium-High
- Regression risk: High
- Interface risk: High (doctor output and execution eligibility may materially change)
- Main failure mode: hardening introduces unexpected blockers for existing migrations.

## Best fit when
You need stronger guarantees and are prepared to absorb compatibility review and potential migration cleanups.
