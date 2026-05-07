Updated in the staged migration workspace:

- `plan.md`
- `phase-1-lock-behavioral-baseline.md`
- `phase-2-refactor-local-control-flow.md`
- `phase-3-regression-proof-and-final-validation.md`

Key fix applied: Phase 2 precondition no longer conflates start-gating with validation outcome. Preconditions are now phase-local/state-based; validation expectations live under `Validation` and `Definition of Done`.
