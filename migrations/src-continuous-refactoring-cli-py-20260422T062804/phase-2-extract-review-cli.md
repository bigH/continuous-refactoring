# Phase 2: Extract Review CLI

## Objective

Move migration review command execution from `cli.py` into `src/continuous_refactoring/review_cli.py` while preserving parser construction and all review behavior.

After this phase, `cli.py` should dispatch review commands through a focused review module instead of owning migration review internals.

## Precondition

Phase 1 is complete. Review behavior is characterized by tests. `cli.py` still owns the review handlers and `review_cli.py` does not exist.

## Scope

Allowed production files:

- `src/continuous_refactoring/cli.py`
- `src/continuous_refactoring/review_cli.py`

Allowed test files:

- `tests/test_cli_review.py`

Allowed test files for export verification only:

- `tests/test_continuous_refactoring.py`

Do not edit `loop.py`, `migrations.py`, `prompts.py`, `agent.py`, or `__init__.py`. If the extraction appears to require changing package-root exports, block and split that public-API decision into a separate plan.

## Instructions

1. Create `src/continuous_refactoring/review_cli.py`.
2. Add `from __future__ import annotations` and an explicit module-local `__all__`.
3. Move review-owned code from `cli.py`:
   - `_REVIEW_USAGE`;
   - review context resolution;
   - list handling;
   - perform handling;
   - review subcommand dispatch.
4. Rename moved helpers without leading underscores if tests need to call them directly:
   - `handle_review`;
   - `handle_review_list`;
   - `handle_review_perform`.
5. Keep parser construction in `cli.py`. `_add_review_parser()` should remain there.
6. Make `cli.py` import only the review dispatch function needed by `_COMMAND_HANDLERS`.
7. Move the `run_agent_interactive` dependency to `review_cli.py`. `cli.py` should still import `run_agent_interactive_until_settled` for taste handling.
8. Retarget tests deliberately:
   - import review helpers from `continuous_refactoring.review_cli`;
   - monkeypatch `continuous_refactoring.review_cli.run_agent_interactive`;
   - avoid private-wrapper expectations in `continuous_refactoring.cli`.
9. Do not leave compatibility wrappers such as `_handle_review_perform` in `cli.py`. These are private test conveniences, not shipped API. If a real public contract appears to require a wrapper, block and split that contract decision into a separate plan.
10. Do not add `review_cli` to `src/continuous_refactoring/__init__.py` `_SUBMODULES`.

## Definition of Done

- `src/continuous_refactoring/review_cli.py` owns review command execution and has an explicit `__all__`.
- `src/continuous_refactoring/cli.py` still owns parser construction and command dispatch, but no longer owns review list/perform internals.
- `cli.py` no longer imports `run_agent_interactive` solely for review.
- Review tests target `continuous_refactoring.review_cli` instead of private review helpers in `continuous_refactoring.cli`.
- All Phase 1 review behavior remains unchanged.
- `review_cli` is directly importable as `continuous_refactoring.review_cli`.
- Package-root exports are unchanged; `review_cli` is not added to `_SUBMODULES`.
- The repository is shippable after this phase.

## Validation

Run:

```sh
uv run pytest tests/test_cli_review.py tests/test_cli_taste_warning.py tests/test_main_entrypoint.py
```

If package import/export behavior is touched or uncertain, also run:

```sh
uv run pytest tests/test_continuous_refactoring.py
```
