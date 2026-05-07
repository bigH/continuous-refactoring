Created in the staged migration workspace:

- `plan.md`
- `phase-1-lock-behavioral-baseline.md`
- `phase-2-refactor-local-control-flow.md`
- `phase-3-regression-proof-and-final-validation.md`

The plan is ordered test-first → refactor → regression proof, includes explicit dependencies and a Mermaid dependency graph, and keeps preconditions phase-local (without restating baseline-green invariants). Each phase has independent validation and clear `## Precondition` vs `## Definition of Done`; only Phase 2 includes `required_effort` metadata (`low`) with a short reason.
