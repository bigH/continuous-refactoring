# Phase 1: Codify Current Behavior in Focused Tests

## Objective
Freeze current `commit_messages` behavior with explicit, example-based tests so later refactor work is contract-constrained.

## Scope
- Modify `tests/test_commit_messages.py`.
- Add or extend examples for:
  - punctuation/casing variants in rationale inputs,
  - whitespace-only rationale and subject/why inputs,
  - placeholder/empty normalization behavior currently relied on.
- No production logic changes in this phase.

## Precondition
- This migration exists and Phase 1 is the next incomplete phase.
- `tests/test_commit_messages.py` and `src/continuous_refactoring/commit_messages.py` exist in the workspace.
- Target symbols covered by the focused tests are present in `commit_messages.py`.

## Validation
- Run: `uv run pytest tests/test_commit_messages.py`
- Confirm the new/updated tests exercise the targeted edge behaviors and pass.

## Definition of Done
- `tests/test_commit_messages.py` contains explicit coverage for the targeted edge cases.
- Focused validation passes.
- Test assertions lock current intended behavior without changing external interfaces.
- Repository remains shippable at phase completion.
