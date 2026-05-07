# Phase 3: Regression Proof and Final Validation

## Objective
Prove migration safety by validating both targeted behavior and full-suite integrity after the refactor lands.

## Scope
- No additional feature/refactor scope.
- Validation and any minimal fixes strictly required to satisfy established Phase 1/2 behavior and full-suite compatibility.

## Precondition
- Phase 2 is complete.
- Phase 1/2 artifacts are present (tests and refactored module).
- No unresolved migration-internal TODOs remain for this target module.

## Validation
- Run focused validation: `uv run pytest tests/test_commit_messages.py`
- Run full validation: `uv run pytest`
- If failures occur, apply minimal corrective edits consistent with earlier phase contracts and re-run both commands.

## Definition of Done
- Focused and full validation commands pass.
- No unresolved regressions remain in `commit_messages` behavior covered by Phase 1.
- The repository is shippable with the migration changes applied.
