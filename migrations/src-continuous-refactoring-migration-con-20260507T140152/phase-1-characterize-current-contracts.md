# Phase 1: Characterize Current Contracts

## Objective
Capture current observable behavior of `migration_consistency` before internal refactoring.

## Scope
- Files in scope:
  - `tests/test_migration_consistency.py`
- Optional minimal fixture updates only when needed by the new/updated assertions.
- Characterize these contracts:
  - Mode-specific blocking semantics.
  - Visible migration directory filtering, including hidden/dotted/internal/symlink exclusion behavior.
  - Phase-doc section requirements (`## Precondition`, `## Definition of Done`).
  - Duplicate phase-doc detection semantics.

## Precondition
- Migration manifest still lists this phase as the current executable phase.
- `src/continuous_refactoring/migration_consistency.py` still defines `check_migration_consistency()`, `has_blocking_consistency_findings()`, and `iter_visible_migration_dirs()`.
- `tests/test_migration_consistency.py` exists and remains the ownership location for module-level consistency behavior tests.

## Implementation Instructions
1. Add or refine assertions against outcomes (finding content and blocking behavior), not implementation details.
2. Keep fixtures compact and local.
3. Avoid unrelated suite rewrites.

## Validation
1. Run targeted tests:
- `uv run pytest tests/test_migration_consistency.py`
2. Run full configured validation command before marking the phase complete.

## Definition of Done
- Module-level consistency contracts needed by downstream phases are explicitly asserted in `tests/test_migration_consistency.py`.
- Added/updated tests fail on contract regressions.
- No public interface changes are introduced.
- Full configured validation command passes.

required_effort: low
effort_reason: Additive characterization work with low structural risk.
