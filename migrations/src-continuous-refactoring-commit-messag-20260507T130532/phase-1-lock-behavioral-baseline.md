# Phase 1: Lock Behavioral Baseline with Focused Tests

## Objective
Codify existing `commit_messages` behavior with focused example-based tests so later refactoring is constrained by explicit outcomes.

## Scope
- Modify `tests/test_commit_messages.py`.
- Add or extend cases for:
  - punctuation and casing variants in rationale inputs,
  - whitespace-only rationale and subject/why segments,
  - placeholder/empty normalization behavior currently relied on.
- No production-code logic changes in this phase.

## Precondition
- The migration exists and this phase is the first incomplete phase.
- `tests/test_commit_messages.py` and `src/continuous_refactoring/commit_messages.py` exist at expected paths.
- No in-progress edits are pending review within this migration workspace.

## Implementation Notes
- Prefer concise, table-like example coverage over broad fixtures.
- Assert output strings and externally visible behavior, not call ordering.
- Keep test naming explicit about the behavior being frozen.

## Validation
- Run: `uv run pytest tests/test_commit_messages.py`
- Confirm new/updated tests fail if behavior contract is intentionally broken, then pass with current behavior.

## Definition of Done
- `tests/test_commit_messages.py` includes explicit coverage for the targeted edge cases.
- Focused test command passes.
- Test expectations reflect current intended behavior without introducing cross-module contract changes.
- Repository remains shippable after the phase.
