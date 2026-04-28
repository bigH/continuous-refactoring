# Phase 4: Loop and CLI resilience under boundary changes

## Objective
Ensure loop and CLI behavior remains shippable when artifact/config/git boundaries fail, with truthful user messaging and unchanged control-flow defaults.

## Scope
- `src/continuous_refactoring/loop.py`
- `src/continuous_refactoring/config.py`
- `src/continuous_refactoring/cli.py`
- `tests/test_cli_init_taste.py`
- `tests/test_cli_taste_warning.py`
- `tests/test_run_once.py`
- `tests/test_run_once_regression.py`
- `tests/test_config.py`
- `tests/test_phases.py`

## Instructions
1. Update boundary catch/relay points in `loop.py` so config/artifacts/git failures are wrapped only at decision points and keep current fallback logic when safe (`load_taste` defaults, non-fatal taste path failures, validation path continuity).
2. Tighten `config.py` helpers (`load_manifest`, `_load_manifest_payload`, and related config loaders) only where needed to align with consistent cause-chaining semantics with artifacts and keep missing-manifest behavior unchanged.
3. Update CLI taste/upgrade/init paths to preserve exact user-facing behavior on boundary failures while adding richer cause-linked debug context internally.
4. Add regression tests for malformed/unreadable manifest and log-write failures in config/CLI/loop surfaces that must not crash into less useful errors.
5. Keep command output and exit status stable where existing tests assert exact semantics.
6. Ensure `tests/test_phases.py` includes migration/tick expectations that still validate unchanged high-level outcomes under loop/cli boundary stress paths.

## Precondition
- Phase 3 complete and passing targeted gates.
- Current behavior in `tests/test_cli_init_taste.py`, `tests/test_cli_taste_warning.py`, `tests/test_run_once.py`, and `tests/test_run_once_regression.py` is green.
- No edits in `__init__.py` in this phase yet.

## Definition of Done
- Loop/CLI/cfg paths remain robust under boundary failures and recover/abort in the same control plane as before.
- Boundary errors are wrapped with preserved causes only where callsite semantics improve context.
- Regressions for taste, run-once, and config load paths are covered by new/updated tests.
- No observable behavior changes outside error-cause channels unless explicitly documented by tests.
- No new direct API behavior changes in this phase outside boundary resilience scope.
- All phase-4 scope tests pass.

## Validation steps
- `uv run pytest tests/test_cli_init_taste.py tests/test_cli_taste_warning.py`
- `uv run pytest tests/test_run_once.py tests/test_run_once_regression.py`
- `uv run pytest tests/test_config.py`
