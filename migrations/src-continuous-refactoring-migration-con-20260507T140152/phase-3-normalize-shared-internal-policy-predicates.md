# Phase 3: Normalize Shared Internal Policy Predicates

## Objective
Consolidate duplicated internal mode/status policy checks into explicit helpers and tighten naming without behavior changes.

## Scope
- Files in scope:
  - `src/continuous_refactoring/migration_consistency.py`
  - Tests updated only when needed to retain clarity and contract coverage.
- Focus areas:
  - Repeated mode/status gating logic.
  - Naming clarity around ready-publish metadata vs planning-required checks.
  - Removal of dead or redundant internal branches.

## Precondition
- Phase 2 is complete and has introduced stable rule-group helper structure.
- Existing finding contracts remain locked by tests.
- No caller API changes are pending for this migration.

## Implementation Instructions
1. Identify duplicated policy predicates and centralize each policy family into one internal helper.
2. Replace call sites incrementally, keeping branch outcomes identical.
3. Delete unreachable/redundant branches once replacement is in place.
4. Keep helper names domain-meaningful and behavior-transparent.

## Validation
1. Run targeted suites:
- `uv run pytest tests/test_migration_consistency.py`
- Additional targeted suites for any consistency consumers affected by predicate consolidation.
2. Run full configured validation command before marking complete.

## Definition of Done
- Duplicated policy predicate logic is consolidated into clear internal helpers.
- Internal naming and control flow are clearer with no caller-facing behavioral drift.
- Consistency finding contracts stay intact under existing and characterization tests.
- Full configured validation command passes.

required_effort: medium
effort_reason: Logic normalization across gating predicates is subtle and regression-prone without careful checks.
