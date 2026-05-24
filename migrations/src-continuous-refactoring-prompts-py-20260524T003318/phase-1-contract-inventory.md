# Phase 1: Contract Inventory

## Objective
Create a precise inventory of prompt contracts in `src/continuous_refactoring/prompts.py` so later consolidation work is constrained by explicit invariants.

## Scope
- Inspect prompt builders/templates in `src/continuous_refactoring/prompts.py`.
- Map repeated required clauses and existing literal contract points.
- Identify test coverage gaps in `tests/test_prompts.py` relative to required invariants.
- No behavior changes.

## Precondition
- Migration status is active for this phase and no earlier phase is incomplete.
- `src/continuous_refactoring/prompts.py` and `tests/test_prompts.py` are present and readable.
- No concurrent edit is in progress on the same migration workspace.

## Implementation Notes
- Produce a short inventory artifact inside this phase document (or a linked note) listing:
  - Required stable prompt sections (including `## Taste` requirements).
  - Contract-sensitive delimiters/phrases used for parsing or downstream decisions.
  - Repetition candidates safe for consolidation without semantic drift.
  - Known risky areas where wording drift could break behavior/tests.
- Keep the inventory grounded in current code and tests, not speculative future shape.

## Validation
- Confirm no code or behavior changed.
- Run targeted prompt tests if needed to confirm baseline understanding:
  - `uv run pytest tests/test_prompts.py`

## Definition of Done
- A concrete inventory of prompt contracts exists and is specific enough to drive Phase 2 edits.
- Repetition/consolidation candidates are identified with explicit “must-preserve” constraints.
- Any ambiguous contract points are called out for conservative handling in later phases.
- The configured validation command passes:
  - `uv run pytest`

## Contract Inventory (Phase 1 Artifact)

### Stable sections that must be preserved
- `compose_full_prompt()` output section shape and order:
  - `Attempt {n}`
  - base prompt body
  - `REQUIRED_PREAMBLE` literal
  - `## Refactoring Taste`
  - optional `## Target Files`
  - optional `## Scope`
  - `## Validation`
  - optional retry-context triple (`## Retry Context`, retry body, warning line)
  - optional fix amendment appended at end
- Taste-injected prompt constants must include both terms checked by tests:
  - contains `"taste"` (case-insensitive)
  - contains `"injected by the caller"`
- Planning expand/review prompts must preserve `## Precondition` vs `## Definition of Done` terminology split and explicit anti-conflation language.
- `DEFAULT_REFACTORING_PROMPT` and `PHASE_EXECUTION_PROMPT` must embed the status block delimiters.

### Contract-sensitive delimiters and phrases
- Status block delimiters are strict literals:
  - `BEGIN_CONTINUOUS_REFACTORING_STATUS`
  - `END_CONTINUOUS_REFACTORING_STATUS`
- Output-contract literals used by downstream parsing/tests:
  - classifier: `decision: cohesive-cleanup`, `decision: needs-plan`
  - final review: `final-decision: approve-auto|approve-needs-human|reject`
  - ready check: `ready: yes|no|unverifiable`
- Driver-ownership clause in default refactor prompt:
  - contains `Do not create git commits yourself.`
- Phase-ready wording guardrails (fresh evidence is not a human-review blocker) are assertion-backed and must remain semantically intact.

### Repetition candidates safe for consolidation (with must-preserve constraints)
- Repeated `"Refactoring taste is injected by the caller..."` lines across classifier/planning/phase/review prompts.
  - Must preserve exact `"injected by the caller"` phrase where currently tested.
- Repeated work-dir/live-dir mutation guard lines in planning/review composed prompts.
  - Must preserve:
    - `Writable target: work dir only.`
    - `Do not mutate the live migration directory.`
- Repeated status block contract text in refactoring/phase-execution prompts.
  - Must preserve all field names and begin/end markers.
- Repeated planning artifact path references (`.planning/state.json`, `.planning/stages/`, approaches path forms).
  - Safe to centralize as constants/helpers if resulting rendered text is unchanged.

### Known risky areas for wording drift
- Contract lines with finite allowed tokens (`decision:*`, `ready:*`, `final-decision:*`) are parser/test sensitive.
- Taste mention tests are substring-based; removing `"injected by the caller"` from any `_TASTE_INJECTED_PROMPTS` member will fail tests.
- `compose_full_prompt()` section ordering is not fully snapshot-tested but is behavior-significant for readability and downstream operator expectations; treat as must-preserve in consolidation.
- `_CONTINUOUS_REFACTORING_STATUS_BLOCK` embedded guidance fields are partially assertion-backed (`commit_rationale`, `why the refactor`) and operationally load-bearing.

### Coverage gaps to handle conservatively in Phase 2
- No test asserts `compose_full_prompt()` section ordering or exact spacing/newline layout.
- No test asserts exact text for many untested prompt constants (e.g., interview/refine/upgrade templates) beyond indirect behavior; avoid semantic rewrites there during consolidation.
- No test directly locks helper-level behavior (`_join_sections`, `_first_scope`, `_retry_context_sections`); preserve behavior when extracting shared builders.
