# Policy Table Normalization

## Strategy
Replace scattered mode/status conditional logic with a single declarative policy matrix that controls which validations run (`missing-plan`, manifest phase metadata, doc contracts, etc.), then route validators through that matrix.

## Why this approach
- Makes consistency behavior auditable in one place.
- Reduces long-term drift between `planning-snapshot`, `ready-publish`, `execution-gate`, and `doctor` semantics.
- Easier to extend when new consistency modes or statuses appear.

## Tradeoffs
- Moderate refactor risk because it touches decision logic that gates execution/publish.
- Requires careful migration of current behavior to avoid subtle policy regressions.
- Higher upfront cognitive load than incremental extraction.

## Estimated phases
1. Codify current behavior as executable tests (`required_effort: medium`)
- Add table-driven tests proving each mode/status combination for each rule family.
- Include negative assertions for rules that must not run in a mode.

2. Introduce policy matrix + adapter (`required_effort: high`)
- Add a policy structure mapping `(mode, manifest.status)` to enabled checks.
- Rewire validators to consult policy instead of bespoke conditionals.

3. Delete legacy gating branches (`required_effort: medium`)
- Remove `_requires_plan` and `_requires_ready_publish_metadata` style duplication once matrix is trusted.
- Keep finding codes/messages stable unless a review-approved behavior change is intentional.

4. Cross-module confidence pass (`required_effort: medium`)
- Validate no behavior drift in `migration_tick`, `migration_cli doctor`, `review_cli`, and `planning_publish` call chains.

## Risk profile
- Delivery risk: Medium
- Regression risk: Medium-High
- Interface risk: Medium (execution/publish eligibility can change if matrix is wrong)
- Main failure mode: mode-policy mismatch causing unexpected execution blocking or missed blocking findings.

## Best fit when
You want durable policy clarity and are willing to spend more effort now to reduce future drift.
