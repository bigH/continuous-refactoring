# Phase 3: Test Hardening

## Objective
Strengthen `tests/test_prompts.py` so core prompt invariants are explicit and resilient to safe refactors while still detecting contract drift.

required_effort: medium
effort_reason: Requires careful test-shape redesign to reduce brittleness without weakening contract checks.

## Scope
- Add/adjust tests for required invariant anchors identified in Phase 1.
- Ensure `## Taste` injection coverage remains explicit across required prompt templates.
- Replace scattered brittle literal checks where appropriate with focused invariant assertions.
- Keep tests outcome-focused; avoid mock-heavy tests unless boundary isolation is necessary.

## Precondition
- Phase 2 consolidation is complete and prompt outputs are stable.
- Invariant anchors to assert are finalized from the contract inventory.
- No unresolved intentional interface-change decisions remain for this migration.

## Implementation Notes
- Prefer assertions on stable contract points (section headers, delimiters, mandatory clauses).
- Keep tests readable and maintainable; avoid overfitting to incidental formatting.
- Preserve or improve failure clarity so regressions identify which contract was broken.

## Validation
- Run prompt tests first:
  - `uv run pytest tests/test_prompts.py`
- Run any additional directly impacted tests.

## Definition of Done
- Tests clearly encode the required prompt invariants and catch meaningful contract regressions.
- Brittle/duplicative literal checks are reduced where they do not represent true contracts.
- Taste injection requirements remain enforced by tests.
- The configured validation command passes:
  - `uv run pytest`
