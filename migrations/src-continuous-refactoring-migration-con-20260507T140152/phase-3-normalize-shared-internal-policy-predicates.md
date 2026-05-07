# Phase 3: Normalize Shared Internal Policy Predicates

## Objective
Consolidate duplicated internal policy predicates and simplify control flow while preserving observable behavior.

## Scope
- Files in scope:
  - `src/continuous_refactoring/migration_consistency.py`
  - `tests/test_migration_consistency.py`
  - `tests/test_migration_tick.py` (only if predicate normalization affects scheduler-facing finding interpretation)
  - `tests/test_migration_cli.py` (only if predicate normalization affects doctor/list-facing finding interpretation)
- Focus areas:
  - Repeated mode/status gating predicates.
  - Redundant branch removal once equivalent shared predicates exist.
  - Domain-meaningful internal naming improvements.

## Precondition
- Phase 2 is complete.
- Rule-group helper seams from Phase 2 exist in `migration_consistency.py` and are the active execution path.
- No concurrent phase is modifying consistency finding schema or public consistency entrypoints.

## Implementation Instructions
1. Centralize each duplicated predicate family into one helper.
2. Replace callers incrementally and keep branch outcomes identical.
3. Remove dead/redundant branches only after replacement coverage is in place.
4. Keep helper names explicit about policy intent.

## Validation
1. Run targeted tests:
- `uv run pytest tests/test_migration_consistency.py`
2. If touched, run:
- `uv run pytest tests/test_migration_tick.py`
- `uv run pytest tests/test_migration_cli.py`
3. Run full configured validation command before marking the phase complete.

## Definition of Done
- Duplicated internal policy predicates are consolidated and control flow is simpler.
- Existing finding contracts remain unchanged under module and touched-consumer tests.
- No public interface changes are introduced.
- Full configured validation command passes.

required_effort: medium
effort_reason: Predicate normalization is subtle and can regress gating semantics without careful checks.
