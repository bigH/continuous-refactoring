# Phase 2 — Boundary-Focused Routing Cleanup

required_effort: medium
effort_reason: Cleanup is local but must preserve subtle boundary semantics while removing duplication.

## Scope
- `src/continuous_refactoring/routing.py`
- `tests/test_routing.py`

## Objectives
- Improve readability and flow in routing classification parsing/failure paths.
- Remove concrete duplication in parse/failure handling without changing observable outcomes.
- Preserve boundary exception semantics and call-finished event expectations.

## Precondition
- Phase 1 is complete.
- `tests/test_cli_version.py` and `tests/test_routing.py` still exist at the Phase 1 paths.
- `src/continuous_refactoring/routing.py` still contains the parse and classify failure paths targeted by this phase.
- No unresolved human-review hold is blocking routing-internal cleanup.

## Implementation Instructions
1. Refactor only within `src/continuous_refactoring/routing.py`.
2. Extract or consolidate duplicated parse/failure logic into small domain-meaningful helpers only where duplication is direct.
3. Keep boundary error translation with exception nesting intact; do not change external status/event contracts.
4. Update `tests/test_routing.py` only as needed to preserve/clarify outcome assertions.

## Validation Steps
1. Run `uv run pytest tests/test_routing.py`.
2. Run the configured full validation command.

## Definition of Done
- `src/continuous_refactoring/routing.py` no longer duplicates parse/failure handling across multiple branches where one helper/path can express the same behavior.
- Observable routing outcomes remain unchanged for existing Phase 1 routing contract assertions in `tests/test_routing.py`.
- Boundary exception chaining behavior is preserved for routing translation failures.
- No files outside Scope were changed.
- Configured full validation command passes.
