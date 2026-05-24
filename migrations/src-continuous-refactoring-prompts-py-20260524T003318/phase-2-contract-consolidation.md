# Phase 2: Contract Consolidation

## Objective
Refactor internal prompt construction in `src/continuous_refactoring/prompts.py` to reduce duplication by introducing small local anchors/helpers while preserving rendered contract semantics.

required_effort: medium
effort_reason: Consolidation changes many string-assembly sites where subtle wording drift could break parsing and tests.

## Scope
- Add/normalize small local constants/helpers for repeated required clauses.
- Replace high-repetition inline phrase assembly with those helpers.
- Keep exports stable unless dead exports are proven unused and explicitly surfaced.
- Avoid module-split or architecture-level refactors.

## Precondition
- Phase 1 contract inventory is complete and available.
- The consolidation target clauses/helpers are identified with explicit must-preserve constraints.
- Current public symbols and call sites that depend on prompt text shape are identified.

## Implementation Notes
- Apply minimal, localized edits in `src/continuous_refactoring/prompts.py`.
- Preserve load-bearing delimiters/headers and required sections verbatim unless an intentional change is documented.
- Favor readability and short helper abstractions; avoid abstraction layers that obscure prompt outputs.

## Validation
- Run prompt-focused tests:
  - `uv run pytest tests/test_prompts.py`
- If any related tests exist for prompt parsing/decisions, run them as targeted smoke checks.

## Definition of Done
- Repeated contract clauses are consolidated into clear local helpers/constants.
- Rendered prompt outputs preserve required semantics from Phase 1 inventory.
- Public/exported behavior remains unchanged unless explicitly documented for review.
- The configured validation command passes:
  - `uv run pytest`
