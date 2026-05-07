# Phase 2: Extract Rule Groups Behind Stable API

## Objective
Refactor `migration_consistency.py` internals into clear rule-group helpers without changing external behavior.

## Scope
- Files in scope:
  - `src/continuous_refactoring/migration_consistency.py`
  - `tests/test_migration_consistency.py` (only for maintenance required by structural refactor)
- Preserve these public function signatures and semantics:
  - `check_migration_consistency()`
  - `has_blocking_consistency_findings()`
  - `iter_visible_migration_dirs()`

## Precondition
- Phase 1 is complete.
- `tests/test_migration_consistency.py` contains the characterization assertions added in Phase 1.
- Callers in the repository still consume consistency checks through the current public functions (no parallel interface migration in progress).

## Implementation Instructions
1. Extract coherent internal helper groups by concern (visibility, manifest checks, phase-file checks, phase-doc checks).
2. Keep top-level control flow explicit so finding emission remains traceable.
3. Preserve finding severity/mode/code/path outputs.
4. Avoid changing caller-facing behavior or data contracts.

## Validation
1. Run targeted tests:
- `uv run pytest tests/test_migration_consistency.py`
2. Run additional directly affected consumer tests if touched.
3. Run full configured validation command before marking the phase complete.

## Definition of Done
- `migration_consistency.py` is reorganized into readable rule-group helpers with equivalent behavior.
- Characterization tests from Phase 1 remain intact and passing without weakened assertions.
- No public interface changes are introduced.
- Full configured validation command passes.

required_effort: medium
effort_reason: Structural extraction at an execution gate needs careful behavior preservation.
