Updated the planning artifacts in the staged migration directory:

- `plan.md`
- `phase-1-characterize-current-contracts.md`
- `phase-2-extract-rule-groups-behind-stable-api.md`
- `phase-3-normalize-shared-internal-policy-predicates.md`
- `phase-4-integration-verification-sweep.md`

What I fixed relative to review findings:

1. Removed baseline-validation language from phase preconditions (no “tests are passing” gating).
2. Replaced weak/non-gating Phase 1 preconditions with concrete structural readiness gates.
3. Tightened Phase 3 scope with explicit file boundaries.
4. Added explicit “No public interface changes” to every phase Definition of Done.
5. Kept phase order risk-reducing, independently verifiable, and shippable per phase with clear validation steps.
