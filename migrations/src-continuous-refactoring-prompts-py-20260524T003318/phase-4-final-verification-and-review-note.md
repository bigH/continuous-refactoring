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

## Interface-Sensitive Wording Delta Enumeration

No intentional interface-level prompt contract change was introduced.

Reviewed potential prompt-surface deltas from Phase 2:
- `compose_full_prompt()` now uses `_validation_section()` and
  `_with_retry_context()`, but still renders the same `## Validation` block and
  keeps retry context before the optional amendment.
- Classifier, scope-selection, planning, phase-ready, phase-execution, and
  migration-review prompts now use `_taste_section()` where they already used a
  `## Taste` section; the section heading and injected taste body are preserved.
- `compose_full_prompt()` still uses `## Refactoring Taste`; that separate
  heading was intentionally not routed through `_taste_section()`.
- Phase execution now uses `_validation_section()` and `_with_retry_context()`,
  preserving the rendered validation and retry-context contract shape.
- Migration review now uses `_WORKSPACE_MUTATION_CONTRACT_LINES`, preserving the
  exact staged/work/live directory mutation guard lines.

Reviewed potential test-surface deltas from Phase 3:
- Output-contract checks were consolidated through helper assertions only.
- New assertions lock section ordering for `compose_full_prompt()` and preserve
  the Phase 1 contract inventory's sensitive anchors.
- No production prompt text is changed by Phase 3.

Contract-sensitive anchors confirmed as preserved:
- `BEGIN_CONTINUOUS_REFACTORING_STATUS`
- `END_CONTINUOUS_REFACTORING_STATUS`
- `decision: cohesive-cleanup` / `decision: needs-plan`
- `ready: yes` / `ready: no` / `ready: unverifiable`
- `final-decision: approve-auto` / `approve-needs-human` / `reject`
- `## Taste`, `## Refactoring Taste`, `## Validation`, and `## Retry Context`
- `Do not mutate the live migration directory.`

## Final Review Note

No human-review-triggering prompt wording delta remains. The migration changed
internal prompt assembly and prompt-test structure while preserving the rendered
contract points identified in Phase 1. Phase 4 can complete without escalating
for human review if the configured validation command passes.

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
