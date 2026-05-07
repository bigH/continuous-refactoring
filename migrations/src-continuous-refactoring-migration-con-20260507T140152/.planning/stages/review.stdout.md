1. `phase-2-extract-rule-groups-behind-stable-api.md` precondition conflates start-gating with validation outcome: “Characterization tests … are present and passing.” Passing test state is harness-owned evidence, not a phase precondition.

2. `phase-4-integration-verification-sweep.md` precondition has the same issue: “all direct module tests pass.” That is baseline/validation evidence, not a concrete structural start gate for the phase.

3. `phase-1-characterize-current-contracts.md` precondition is partly weak/non-gating: “No earlier phase is required” and “workspace paths … are intact” don’t materially gate execution beyond environment assumptions. Replace with concrete repo-state conditions that determine readiness.

4. `phase-3-normalize-shared-internal-policy-predicates.md` scope is too loose for a low-risk refactor phase (“Tests updated only when needed…” without enumerating candidate files), which weakens the “no out-of-scope source edits” guarantee. Add explicit file boundaries similar to phase 4’s test-file list.

5. Plan respects refactoring taste overall (behavior-preserving, interface caution, minimal comments/abstractions, no speculative architecture), but phase docs should explicitly restate “no public interface changes” in each phase DoD to keep taste-aligned review clarity phase-local rather than only in top-level plan.
