# Phase 3: Regression Validation and Closeout

## Objective
Prove migration safety with focused and full-suite validation after Phase 2 lands.

## Scope
- No new feature/refactor scope.
- Validation and only minimal corrective edits needed to satisfy prior phase contracts.

## Precondition
- Phase 2 is complete.
- Phase 1 tests and Phase 2 refactor edits are present in the workspace.
- No unresolved migration-internal blockers remain for this target.

## Validation
- Run focused validation: `uv run pytest tests/test_commit_messages.py`
- Run full validation: `uv run pytest`
- If failures occur, apply minimal corrections consistent with Phases 1-2 contracts and re-run both commands.

## Definition of Done
- Focused and full validation commands pass.
- No unresolved regressions remain in behavior covered by Phase 1.
- Repository remains shippable at phase completion.
