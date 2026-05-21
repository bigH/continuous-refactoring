# Phase 3: Interface-Shift Review Gate

## Goal
Gate any interface behavior change behind explicit, interface-specific human review before automation continues.

## Scope
- Executes only when Phase 2 identifies an interface behavior delta.
- Documentation and migration state updates required to communicate and enforce review gating.
- Technical code changes are minimal and limited to what is necessary for correct gating-state behavior.

## Precondition
- Phase 2 is complete.
- At least one concrete interface behavior delta is documented with reproducible before/after behavior.
- The migration still has `awaiting_human_review` unset at phase start, so this phase can set and verify the gate.

## Implementation Instructions
1. Document each interface shift with concrete before/after behavior and user/install impact.
2. Add explicit review messaging that names the exact interface contract change; avoid generic "needs review" wording.
3. Set and verify `awaiting_human_review` gating so automation remains paused until canonical migration review approval.
4. Keep non-gating technical churn out of this phase.

## Validation Steps
1. Verify review artifacts clearly describe each interface delta and impact.
2. Verify migration gating state correctly reflects pending human review.
3. Run the configured full validation command after artifact/state updates.

## Definition of Done
- All interface behavior changes discovered in this migration are documented with concrete impact statements.
- Human-review gating is active, explicit, and tied to the named interface deltas.
- Review text is interface-specific and non-generic.
- The full configured validation command passes.

required_effort: medium
effort_reason: Primarily documentation plus gating-state correctness with limited code-path change.
