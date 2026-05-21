# Phase 1: Boundary Contract Guardrails

## Scope
- `tests/test_prompts.py`
- `tests/test_loop_migration_tick.py`
- `.github/workflows/pr-title.yml` (tests/fixtures/assertions only; no policy change in this phase)
- Any directly related existing tests that validate the same boundary contracts

## Goals
- Lock current interface behavior with outcome-focused tests before internal refactors.
- Increase confidence around effort-cap behavior and planning gating behavior.
- Make PR title policy edge behavior explicit in testable checks without changing policy semantics.

## Precondition
- No earlier phase in this migration is incomplete.
- Files/symbols defining current effort routing, migration ticking/planning gating, prompt taste injection, and PR title validation still exist and are reachable from tests.
- The worktree contains no unrelated in-flight edits to the same boundary files that would make observed behavior ambiguous.

## Implementation Instructions
1. Strengthen/extend tests for migration ticking and planning gating behavior so they assert outcomes (eligibility/deferral/routing), not internal call shapes.
2. Strengthen/extend prompt contract tests only for load-bearing invariants (including Taste section and staged/live planning constraints where already contractual).
3. Add explicit PR-title edge-case checks in workflow-adjacent test coverage/fixtures or equivalent deterministic assertions, while preserving current acceptance behavior.
4. Keep changes small and focused on guardrails; do not refactor production logic in this phase unless needed to enable deterministic testing.

## Validation Steps
- Run targeted checks first:
  - `uv run pytest tests/test_prompts.py`
  - `uv run pytest tests/test_loop_migration_tick.py`
  - `uv run pytest -k "pr title or pr_title"`
- Run full validation command:
  - `uv run pytest`

## Definition of Done
- Boundary tests covering effort-capped migration/planning behavior and prompt contract invariants are present, deterministic, and passing.
- PR title policy behavior is more explicitly exercised without changing acceptance semantics.
- Full configured validation command passes.
- Repository remains shippable with unchanged external interface behavior.
