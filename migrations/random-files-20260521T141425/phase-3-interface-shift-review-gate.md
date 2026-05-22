# Phase 3: Interface-Shift Review Gate

## Goal
Gate any discovered interface behavior change behind explicit, interface-specific human review before automation proceeds.

## Scope
- Runs only if Phase 2 identifies at least one interface behavior delta.
- Documentation and migration state updates needed to communicate and enforce review gating.
- No unrelated cleanup or broad production refactor work.

## Precondition
- Phase 2 is complete.
- At least one concrete interface behavior delta is documented with reproducible before/after behavior.
- The migration has not already been marked `awaiting_human_review` for the same deltas.

## Implementation Instructions
1. Document each interface shift with concrete before/after behavior and user/install impact.
2. Ensure review messaging names the exact interface contract change; avoid generic "needs review" language.
3. Set and verify `awaiting_human_review` so automation remains paused until canonical migration review approval.
4. Keep this phase focused on gating correctness and communication quality.

## Validation Steps
1. Verify review artifacts clearly and specifically describe each interface delta and impact.
2. Verify migration gating state is active and accurately tied to the documented deltas.
3. Run the configured full validation command after artifact/state updates.

## Definition of Done
- All interface behavior changes discovered in this migration are documented with concrete impact statements.
- Human-review gating is active, explicit, and tied to the named interface deltas.
- Review messaging is interface-specific and non-generic.
- The full configured validation command passes.

required_effort: high
effort_reason: This phase controls release-facing interface risk and human-review gating correctness, so mistakes can unblock unsafe automation.
