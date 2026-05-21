# Phase 3: Interface-Shift Review Gate

## Goal
Apply explicit human review gating for any interface behavior change introduced or required by the migration.

## Scope
- Runs only when Phase 2 identifies an interface delta.
- Documentation and manifest/review-state updates needed to gate automation until human approval.
- Interface deltas include CLI behavior, repo-written files, XDG/project state behavior, migration manifest structure, and other user/install-visible contract changes.

## Precondition
- Phase 2 is complete.
- A concrete interface behavior delta is identified and reproducible.
- The migration includes clear artifacts describing the before/after behavior and rollout impact.

## Implementation Instructions
1. Document the exact interface change in migration artifacts with concrete before/after behavior.
2. Record explicit human-review-needed messaging naming the specific interface contract shift and user impact.
3. Ensure automation remains gated (`awaiting_human_review`) until canonical migration review clears it.
4. Keep technical changes minimal in this phase: this is a review gate, not a broad additional refactor.

## Validation Steps
1. Verify review-facing artifacts clearly describe the interface delta and impact.
2. Verify migration state correctly reflects human-review gating.
3. Run the configured full validation command after any code/artifact updates.

## Definition of Done
- Every interface behavior change introduced by this migration is explicitly documented with concrete impact.
- Human-review gating is active and unambiguous until review approval.
- No generic "needs review" text is used where interface-specific messaging is required.
- The full configured validation command passes.

required_effort: high
effort_reason: Interface-change triage and review gating is high-stakes and must be exact.
