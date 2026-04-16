# Phase 4 — Validation lock and regression hardening

## Scope (hard allowed set)

- `tests/test_continuous_refactoring.py`
- `tests/test_git_branching.py`
- `tests/test_run_once.py`
- `tests/test_run.py`
- `tests/test_phases.py`
- `tests/test_loop_migration_tick.py`

No source code edits in `src/` are allowed in this phase.

## Goal

Add and execute a migration lock set that proves:
- boundary exception causality is preserved where expected,
- success-path behavior in command and loop wrappers stays stable,
- each prior phase can be independently verified from this phase’s test list.

## Ready when (machine-checkable)

- All listed test commands pass.
- `git diff --name-only` for phase 4 includes only files in this scope.
- For each phase:
  - phase 1 focused checks pass (boundary wrapping on spawn/log creation),
  - phase 2 focused checks pass (interactive spawn wrapping + terminal restoration),
  - phase 3 focused checks pass (maybe_run_agent/run_tests boundary consistency),
  - plus cross-surface integration checks (run-loop and phase readiness paths) pass.
- New tests include explicit assertions on `__cause__` and exact unchanged success outputs where applicable.

## Detailed instructions

1. Add/finish regression tests for boundary contract observability:
   - `run_observed_command` bad launch/log path retains `__cause__`.
   - `run_agent_interactive` and `run_agent_interactive_until_settled` bad launch retains `__cause__`.
   - `run_tests` malformed command retains `__cause__`.
2. Add success-path invariant checks to guard behavioral drift:
   - `maybe_run_agent` with a stubbed valid command returns `CommandCapture.returncode == 0` and non-empty `stdout_path` file writes.
   - existing phase/loop retry and ready-check tests still pass unchanged.
3. Keep terminal-state tests in `test_continuous_refactoring.py` explicit and deterministic (no timing flake dependencies).
4. Keep all new tests close to the owning module in file structure and free of redundant behavioral mocks unless boundary failure injection requires one.

## Validation (required command list)

- Phase lock subset:
  - `uv run pytest tests/test_continuous_refactoring.py::test_run_observed_command_writes_timestamped_logs tests/test_git_branching.py::test_run_observed_command_timeout tests/test_git_branching.py::test_agent_killed_when_stdout_stalled`
  - `uv run pytest tests/test_continuous_refactoring.py::test_run_agent_interactive_until_settled_requests_graceful_exit_after_settle tests/test_continuous_refactoring.py::test_run_agent_interactive_until_settled_ignores_stale_settle_file tests/test_continuous_refactoring.py::test_run_agent_interactive_until_settled_restores_terminal_state_and_codex_modes tests/test_continuous_refactoring.py::test_run_agent_interactive_until_settled_skips_codex_reset_on_clean_exit`
  - `uv run pytest tests/test_continuous_refactoring.py::test_run_tests_rejects_bad_command_string_with_cause tests/test_continuous_refactoring.py::test_maybe_run_agent_preserves_cause_from_build_or_observed_command tests/test_continuous_refactoring.py::test_build_command_rejects_unknown_agent`
- Cross-surface and integration:
  - `uv run pytest tests/test_run_once.py::test_run_once_validation_gate tests/test_run_once.py::test_run_once_no_fix_retry tests/test_run.py::test_run_once_validation_gate`
  - `uv run pytest tests/test_phases.py::test_check_ready_yes tests/test_phases.py::test_check_ready_rejects_unparseable_output`
  - `uv run pytest tests/test_loop_migration_tick.py`
- Final gate:
  - `uv run pytest tests/test_continuous_refactoring.py tests/test_git_branching.py tests/test_run_once.py tests/test_run.py tests/test_loop_migration_tick.py tests/test_phases.py`

## Note

This phase is a pure validation phase. No feature behavior changes or additional refactors are permitted.

