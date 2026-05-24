# Phase 4: Final Verification and Review Note

## Objective
Perform final verification and produce a concise review note confirming contract preservation or clearly surfacing any intentional interface-level wording change.

## Scope
- Final pass on changed prompt/test files for readability and contract consistency.
- Execute full validation.
- Record review note for human review if any user-visible/interface-sensitive text shape changed intentionally.

## Precondition
- Phases 1–3 are complete.
- Consolidated prompt logic and hardened tests are merged in this migration workspace.
- Any potential interface-sensitive wording deltas are enumerated.

## Implementation Notes
- Validate against Phase 1 inventory and Phase 3 assertions.
- If no interface change occurred, explicitly state that in the review note.
- If interface change occurred, name exact behavior/text-shape deltas and rationale.

## Validation
- Run full suite:
  - `uv run pytest`

## Definition of Done
- Final verification confirms the repository remains shippable after this migration.
- A review note exists that either:
  - confirms no intentional interface-level prompt contract change, or
  - explicitly documents each intentional interface-level change for human review.
- No open migration-phase blockers remain.
- The configured validation command passes:
  - `uv run pytest`
