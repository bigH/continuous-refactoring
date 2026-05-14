1. `phase-3-prompt-test-consistency-reconciliation.md` scope is too loose for the “no source changes outside migration scope” rule: it allows “Only additional files directly required…”, which can expand beyond the explicit target set without a hard boundary. Tighten this to an enumerated allowlist (or a clearly bounded file class) so scope drift is impossible.

2. `phase-1-boundary-contract-tests.md` has a partially non-verifiable completion criterion: “tests … reliably fail when those boundary behaviors are intentionally broken.” That is directionally right, but not concretely assessable during normal phase completion. Add an explicit, checkable criterion (for example, required assertions/cases added per contract surface) so phase completion does not depend on hypothetical mutation testing.

3. `phase-2-boundary-helper-refactor.md` `required_effort: medium` is plausible, but the `effort_reason` is generic. Make it operationally useful by tying it to concrete risk points in this phase (for example, ordering preservation in candidate enumeration and deferral write timing), so future runs can quickly judge whether `medium` is still the lowest safe tier.

4. `phase-3-prompt-test-consistency-reconciliation.md` has no explicit `required_effort`/`effort_reason`. Given your effort-budget workflow, add `required_effort: low` with a short reason to make scheduler behavior explicit and consistent across phases.

5. Plan-level and phase-level docs are otherwise solid on ordering, dependency shape, and taste alignment: preconditions are distinct from Definitions of Done, and none of the preconditions improperly restate harness-owned baseline-green invariants (no “tests pass now/full suite passes” style gating).
