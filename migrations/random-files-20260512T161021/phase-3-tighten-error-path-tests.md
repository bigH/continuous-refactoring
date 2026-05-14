# Phase 3: Tighten Error-Path Tests

## Scope
- `tests/test_git.py`
- Focused sections of `tests/test_phases.py`
- Focused sections of `tests/test_planning_publish.py`

## Goals
1. Align tests to assert boundary error behavior by outcomes, not incidental internal call structure.
2. Verify message anchors and `__cause__` preservation introduced/standardized in Phase 2.
3. Reduce brittle or duplicated failure-path assertions.

## Precondition
- Phase 2 is complete and boundary translation behavior is stable in scoped modules.
- Test files listed in Scope still contain the failure-path suites covering those boundaries.
- No pending unresolved edits in scoped runtime modules that would invalidate finalized error semantics for this migration.

## Implementation Instructions
1. Update assertions to check:
   - expected boundary exception type,
   - stable message fragments/anchors,
   - cause-chain shape (`exc.__cause__` and relevant cause type/message where appropriate).
2. Replace duplicated assertion patterns with concise helper logic only when it improves readability.
3. Keep tests outcome-focused; avoid asserting internal call ordering unless load-bearing.

## Validation Steps
1. Run targeted test files:
   - `uv run pytest tests/test_git.py tests/test_phases.py tests/test_planning_publish.py`
2. Run full validation command:
   - `uv run pytest`

## Definition of Done
- Scoped tests validate boundary error type, semantic message anchors, and cause preservation.
- Failure-path assertions are less brittle and avoid unnecessary implementation coupling.
- Test updates reflect actual boundary contracts after Phase 2 without broadening public interface expectations.
- Full validation command `uv run pytest` passes.
