# Phase 4: Contract Sweep

## Objective

Clean up after the extraction and verify the CLI, review boundary, package exports, and docs still describe the shipped behavior.

This phase should be boring. If it discovers a larger design problem, document it instead of expanding scope.

## Precondition

Phases 1 through 3 are complete. Review command execution lives in `review_cli.py`; run dispatch remains in `cli.py`; focused review, run, and command-dispatch tests pass.

## Scope

Allowed production files:

- `src/continuous_refactoring/cli.py`
- `src/continuous_refactoring/review_cli.py`
- `AGENTS.md` only if repo guidance is stale or a new durable invariant must be recorded

Allowed test files:

- `tests/test_cli_review.py`
- `tests/test_focus_on_live_migrations.py`
- `tests/test_run.py`
- `tests/test_cli_taste_warning.py`
- `tests/test_main_entrypoint.py`
- `tests/test_continuous_refactoring.py`

Do not broaden this phase into a taste command extraction or full command-module split.
Do not edit `src/continuous_refactoring/__init__.py` in this phase. Package-root exports must be verified unchanged. If a public export change appears necessary, block and split that into a separate plan.

## Instructions

1. Search for stale private review references:
   - `_handle_review`;
   - `_handle_review_list`;
   - `_handle_review_perform`;
   - `continuous_refactoring.cli.run_agent_interactive` in review tests.
2. Remove unused imports from `cli.py` and `review_cli.py`.
3. Confirm `cli.py` still exports only the intended public CLI surface:
   - `build_parser`;
   - `cli_main`;
   - `parse_max_attempts`;
   - `parse_sleep_seconds`.
4. Confirm `review_cli.py` has a narrow module-local `__all__`.
5. Confirm `src/continuous_refactoring/__init__.py` package-root exports are unchanged and `review_cli` is not included in `_SUBMODULES`.
6. Run package import tests to verify the unchanged export contract.
7. Review `AGENTS.md`:
   - update it if it still says there is no active CLI migration;
   - add a short invariant only if the review boundary or root-export decision is load-bearing for future agents;
   - do not add a long process note.
8. Read the final diff with a maintainer lens:
   - no review behavior changed accidentally;
   - no run behavior changed accidentally;
   - no dead wrappers or compatibility aliases remain;
   - no comments were added where clearer names carry the intent.

## Definition of Done

- No stale review helper references remain in `cli.py` or tests.
- `cli.py` contains generic CLI wiring, taste/init/upgrade handling, and run dispatch guards, but not migration review list/perform internals.
- `review_cli.py` contains only review command behavior and its direct dependencies.
- Package-root exports are unchanged; `review_cli` is not added to `_SUBMODULES`.
- `AGENTS.md` is either still truthful or updated with a tight, durable note.
- Full test suite passes.
- The repository is shippable after this phase.

## Validation

Run the focused gate:

```sh
uv run pytest tests/test_cli_review.py tests/test_focus_on_live_migrations.py tests/test_run.py tests/test_cli_taste_warning.py tests/test_main_entrypoint.py tests/test_continuous_refactoring.py
```

Then run the full gate:

```sh
uv run pytest
```
