# Phase 4: Boundary resilience in callers and prompt/shell consumers

## Objective
Keep adjacent cluster modules robust against stricter config boundary errors without changing cluster-wide behavior.

## Scope
- `AGENTS.md`
- `src/continuous_refactoring/config.py`
- `src/continuous_refactoring/loop.py`
- `src/continuous_refactoring/cli.py`
- `src/continuous_refactoring/prompts.py`
- `src/continuous_refactoring/agent.py`
- `src/continuous_refactoring/artifacts.py`
- `src/continuous_refactoring/failure_report.py`
- `src/continuous_refactoring/git.py`
- `src/continuous_refactoring/review_cli.py`
- `tests/test_cli_taste_warning.py`
- `tests/test_cli_upgrade.py`
- `tests/test_cli_init_taste.py`
- `tests/test_run_once_regression.py`
- `tests/test_config.py`

## Instructions
1. Keep `config.py` public API unchanged.
2. Keep `load_taste()` as the public boundary, but translate unreadable project/global taste reads into `ContinuousRefactorError` with the original `OSError` as the cause.
3. Update `loop._load_taste_safe()` to keep the existing fallback chain:
   - config/project resolution failures should fall back to `load_taste(None)`,
   - unreadable global taste should finally fall back to `default_taste_text()`,
   - no raw `OSError`/`PermissionError` should escape.
4. Keep `loop._resolve_live_migrations_dir()` behavior unchanged; the current fallback semantics already satisfy this phase and should not regress.
5. Update `cli._maybe_warn_stale_taste()` so config/taste-read failures use the same skip-without-crashing path as an unregistered project.
6. Keep `prompts.py` unchanged unless config boundary behavior changes demand otherwise; document any required change explicitly if it occurs.
7. Confirm `agent.py`, `artifacts.py`, `failure_report.py`, `git.py`, and `review_cli.py` need no callsite changes and remain API-compatible.
8. Add regression coverage where the repo currently asserts this behavior:
   - `tests/test_config.py` for `load_taste()` read-fault translation,
   - `tests/test_cli_taste_warning.py` for unreadable taste warning resilience,
   - `tests/test_run_once_regression.py` for loop fallback to default taste.
9. Keep existing `tests/test_cli_init_taste.py` and `tests/test_cli_upgrade.py` behavior green; do not add synthetic signature-lock tests unless the public config API actually changes.

## Precondition
- Phase 3 is complete in migration status and `uv run pytest tests/test_config.py` passes.
- `uv run pytest tests/test_cli_init_taste.py tests/test_cli_upgrade.py tests/test_run_once_regression.py` pass on the current tree.
- No private helper name added in phase 2/3 is imported from `continuous_refactoring.config` outside `config.py`.
  - Concrete check: no `from continuous_refactoring.config import _...` in `src/continuous_refactoring` or cluster test modules.

## Definition of Done
- `config.load_taste()` translates unreadable taste-file reads into `ContinuousRefactorError` without changing its call signature.
- `loop` and `cli` remain resilient when manifest/taste resolution fails (missing file, malformed JSON, unreadable file) and continue with the existing global/default taste fallback behavior.
- `prompts.py` has no user-facing prompt-shape change unless explicitly required by test.
- No callsite API/signature changes to `config.py` are needed in `agent.py`, `artifacts.py`, `failure_report.py`, `git.py`, or `review_cli.py`.
- No module in the migration scope imports private config internals.
- Targeted regression tests for `tests/test_config.py`, `tests/test_cli_taste_warning.py`, `tests/test_cli_init_taste.py`, `tests/test_cli_upgrade.py`, and `tests/test_run_once_regression.py` pass.
- Public behavior from `tests/test_cli_init_taste.py` and `tests/test_cli_upgrade.py` remains backward-compatible.

## Validation steps
- `uv run pytest tests/test_cli_taste_warning.py tests/test_cli_init_taste.py tests/test_cli_upgrade.py`
- `uv run pytest tests/test_run_once_regression.py`
- `uv run pytest tests/test_config.py`
- `uv run pytest`
