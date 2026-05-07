Created the full planning set in the staged migration workspace:

- `plan.md`
- `phase-1-characterize-current-contracts.md`
- `phase-2-extract-rule-groups-behind-stable-api.md`
- `phase-3-normalize-shared-internal-policy-predicates.md`
- `phase-4-integration-verification-sweep.md`

The plan includes numbered phases, a dependency graph, shippability guarantees, and per-phase validation strategy.  
Each phase file includes scope, `## Precondition`, `## Definition of Done`, validation steps, and `required_effort`/`effort_reason` using valid labels (`low`/`medium`) with phase-local preconditions (no baseline-green restatements).
