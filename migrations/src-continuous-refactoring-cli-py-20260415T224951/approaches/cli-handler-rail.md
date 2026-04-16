# Approach: cli-handler-rail

## Strategy
Refactor CLI command dispatch in `cli.py` into explicit handler rails so command resolution is deterministic and discoverable without stringly-typed lookups.

Replace the current `dict`/`getattr` indirection and scattered mode checks with:
- explicit command enum or small handler table
- shared pre-dispatch checks for `taste` mode and targeting gates
- one `dispatch` path that only translates `ContinuousRefactorError` at the boundary

Preserve public flags and output formatting while reducing accidental dispatch drift.

## Why this approach fits the migration
The current handlers are tightly scoped already, but dispatch is split across globals and mode checks. A handler rail makes behavior easier to audit (`run-once`, `run`, `review`, `taste`, `upgrade`) and leaves room for safer static checks as this cluster evolves.

## Tradeoffs
1. Pros: easier to reason about command-to-handler mapping, lower chance of broken dispatch due refactor, better testability for handler selection.
2. Pros: fewer `getattr` paths means clearer traceback origin at module boundaries.
3. Cons: code churn around parser setup and tests that assert `parser` internals; behavior must be preserved exactly.
4. Cons: small up-front taxonomy change might obscure very local tests that monkeypatch by attribute name.

## Estimated phases
1. Introduce a tiny `CliCommand` struct (name, parser builder, handler) or typed handler mapping.
2. Convert `_COMMAND_HANDLERS` and `_REVIEW_HANDLERS` into explicit immutable maps with no string-based handler discovery.
3. Collapse mode preconditions (`_active_taste_mode`, action flag checks, `_handle_taste`) into one explicit decision helper.
4. Simplify `_run_with_loop_errors` usage so loop errors are mapped once and only once.
5. Keep public parser/help strings unchanged and update tests for command resolution and error paths.

## Validation
1. `uv run pytest tests/test_run.py tests/test_cli_init_taste.py tests/test_cli_review.py`
2. `uv run pytest tests/test_taste_interview.py tests/test_taste_refine.py tests/test_taste_upgrade.py tests/test_cli_taste_warning.py`
3. `uv run pytest tests/test_continuous_refactoring.py::test_package_exports_are_stable`

## Risk profile
- Risk level: medium.
- Primary technical risk is regressions in handler/error behavior surfaced by many CLI-focused tests.
- Operational risk is contained; no migration-state logic is touched and no runtime rollout flags are introduced.
