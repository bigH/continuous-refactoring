# Phase 4: Boundary resilience in callers and prompt/shell consumers

## Objective
Keep adjacent cluster modules robust against stricter config boundary errors without changing cluster-wide behavior.

## Scope
- `src/continuous_refactoring/config.py`
- `src/continuous_refactoring/loop.py`
- `src/continuous_refactoring/cli.py`
- `src/continuous_refactoring/prompts.py`
- `src/continuous_refactoring/agent.py`
- `src/continuous_refactoring/artifacts.py`
- `src/continuous_refactoring/git.py`
- `tests/test_cli_init_taste.py`
- `tests/test_cli_upgrade.py`
- `tests/test_run_once_regression.py`
- `tests/test_config.py`

## Instructions
1. Keep `config.py` public API unchanged.
1. Update `loop._load_taste_safe()` to treat `ContinuousRefactorError` from `resolve_project()` and `load_taste()` as non-fatal and continue with default taste.
2. Update `loop._resolve_live_migrations_dir()` to keep existing fallback semantics when config boundaries fail.
3. Update `cli._maybe_warn_stale_taste()` so config resolution failures funnel into the same warn-or-skip path as existing stale-taste behavior, with no crash.
4. Keep `prompts.py` unchanged unless config boundary behavior changes demand otherwise; document any required change explicitly if it occurs.
5. Confirm `agent.py`, `artifacts.py`, and `git.py` need no callsite changes and remain API-compatible.
6. Add a regression test in `tests/test_cli_init_taste.py` that malformed manifest content in app data does not crash stale-taste warning logic.
7. Add a regression test in `tests/test_run_once_regression.py` that run-once still resolves and defaults taste when manifest load fails.
8. Add a smoke contract test in `tests/test_cli_upgrade.py` that verifies no public `config` call signatures changed by this migration.

## Precondition
- Phase 3 is complete in migration status and `uv run pytest tests/test_config.py` passes.
- `uv run pytest tests/test_cli_init_taste.py tests/test_cli_upgrade.py tests/test_run_once_regression.py` pass on the current tree.
- No private helper name added in phase 2/3 is imported from `continuous_refactoring.config` outside `config.py`.
  - Concrete check: no `from continuous_refactoring.config import _...` in `src/continuous_refactoring` or cluster test modules.

## Definition of Done
- `loop` and `cli` remain resilient when manifest/taste resolution fails (missing file, malformed JSON, unreadable file) and continue with default taste resolution.
- `prompts.py` has no user-facing prompt-shape change unless explicitly required by test.
- No callsite API/signature changes to `config.py` are needed in `agent.py`, `artifacts.py`, `git.py`.
- No module in the migration scope imports private config internals.
- Targeted regression tests for the three cluster suites and `tests/test_config.py` pass.
- Public behavior from `tests/test_cli_init_taste.py` and `tests/test_cli_upgrade.py` remains backward-compatible.

## Validation steps
- `uv run pytest tests/test_cli_init_taste.py tests/test_cli_upgrade.py`
- `uv run pytest tests/test_run_once_regression.py`
- `uv run pytest tests/test_config.py`
- `uv run pytest`
