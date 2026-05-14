# Phase 1 — Freeze Interface Contracts

required_effort: low
effort_reason: External contract lock-in is narrow and test-first.

## Scope
- `src/continuous_refactoring/__main__.py`
- `tests/test_cli_version.py`
- `tests/test_routing.py`

## Objectives
- Make `python -m continuous_refactoring` and `--version` behavior explicit and regression-resistant.
- Tighten routing parse/error invariants at the module boundary without broad structural changes.
- Ensure any interface-significant behavior change is explicitly surfaced for human review.

## Precondition
- Migration status is ready for execution and this phase is the manifest current phase.
- No incomplete edits from earlier aborted attempts remain in scoped files.
- Expected interface files and tests listed in Scope exist at their known paths.
- No unresolved review/human-decision hold specific to this phase’s interface contracts.

## Implementation Instructions
1. Add or tighten example-based tests that pin module-entry and version output behavior.
2. Strengthen routing boundary tests for parse success/failure invariants and stable error translation behavior.
3. Make minimal production changes needed to satisfy tests while preserving existing boundary exception nesting expectations.
4. Avoid speculative refactors; only contract-hardening edits in this phase.

## Validation Steps
1. Run targeted tests for touched interface/routing test modules.
2. Run the configured full validation command.

## Definition of Done
- Module entrypoint and `--version` behavior are explicitly covered by stable tests.
- Routing boundary parse/error invariants are explicitly covered by tests.
- Production code changes are limited to contract-hardening required by those tests.
- Configured full validation command passes.
