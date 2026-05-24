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
