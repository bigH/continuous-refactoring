# Phase 2: Extract Rule Groups Behind Stable API

## Objective
Refactor `migration_consistency.py` internals into clear rule-group helpers while preserving existing public API and behavior.

## Scope
- Files in scope:
  - `src/continuous_refactoring/migration_consistency.py`
  - `tests/test_migration_consistency.py` (only for test maintenance when structurally needed)
- Keep externally consumed function signatures unchanged:
  - `check_migration_consistency()`
  - `has_blocking_consistency_findings()`
  - `iter_visible_migration_dirs()`

## Precondition
- Phase 1 is complete and merged into this migration branch.
- Characterization tests for current contracts are present and passing.
- Existing call sites still depend on current public function names/signatures.

## Implementation Instructions
1. Introduce small internal helpers grouped by concern (for example directory visibility rules, manifest integrity rules, phase file integrity rules, phase-doc contract rules).
2. Keep data flow explicit from top-level check entrypoint to emitted findings.
3. Preserve finding codes, severities, modes, and path semantics.
4. Avoid changing caller-facing behavior, CLI semantics, or manifest structure contracts.

## Validation
1. Run targeted suite:
- `uv run pytest tests/test_migration_consistency.py`
2. Run adjacent targeted suites that consume consistency findings if touched indirectly.
3. Run full configured validation command before marking complete.

## Definition of Done
- `migration_consistency.py` is structurally split into readable rule-group helpers.
- Public APIs and externally observable behavior remain unchanged.
- Characterization tests from Phase 1 pass without being weakened.
- Full configured validation command passes.

required_effort: medium
effort_reason: Structural extraction in a sensitive execution gate requires careful behavior preservation.
