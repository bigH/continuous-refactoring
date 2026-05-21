Updated in the staged migration workspace:

- `plan.md`
- `phase-1-contract-regression-net.md`
- `phase-2-internal-cleanup-behind-contracts.md`
- `phase-3-interface-shift-review-gate.md`

Review findings addressed:

1. Phase 3 effort lowered from `high` to `medium` with rationale aligned to minimal technical scope.
2. Phase 1 precondition tightened to a binary artifact gate: required `phase-1-contract-inventory.md`.
3. Phase 2 moved deletion-proof requirement out of precondition into validation/DoD; precondition is now dependency/scope readiness only.

The phases remain ordered for risk reduction, independently verifiable, and shippable at each step.
