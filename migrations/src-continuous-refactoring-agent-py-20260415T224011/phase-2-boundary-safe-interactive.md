# Phase 2 — Boundary-safe interactive execution in `agent.py`

## Scope (hard allowed set)

- `src/continuous_refactoring/agent.py` (only)
  - `run_agent_interactive`
  - `run_agent_interactive_until_settled`
- `tests/test_continuous_refactoring.py` (add/update)

No other file is editable in this phase.

## Goal

Apply the same boundary translation style used in phase 1 to interactive spawn paths, preserving causes and ensuring terminal restoration remains intact.

## Ready when (machine-checkable)

- Targeted tests pass:
  - `uv run pytest tests/test_continuous_refactoring.py::test_run_agent_interactive_until_settled_restores_terminal_state_and_codex_modes`
  - `uv run pytest tests/test_continuous_refactoring.py::test_run_agent_interactive_until_settled_skips_codex_reset_on_clean_exit`
  - `uv run pytest tests/test_continuous_refactoring.py::test_run_agent_interactive_until_settled_requests_graceful_exit_after_settle`
- For a missing interactive executable:
  - `run_agent_interactive(..., agent="does-not-exist", ...)` raises `ContinuousRefactorError`
    with non-`None` `__cause__`.
- For an invalid working directory:
  - `run_agent_interactive_until_settled(..., repo_root=Path("/does/not/exist"))` raises `ContinuousRefactorError`
    with non-`None` `__cause__`.
- No changes required to `loop.py` or `phases.py` for phase 2 to merge.

## Detailed instructions

1. Wrap `subprocess.Popen(...)` in `run_agent_interactive` with:
   - boundary-level message
   - `from error`
2. Wrap `subprocess.Popen(...)` in `run_agent_interactive_until_settled` with the same policy.
3. Keep terminal lifecycle unchanged:
   - `terminal_state` capture/restore flow,
   - forced codex stop/reset behavior,
   - `finally` ordering and cleanup calls.
4. Do not modify settlement decision logic.
5. Do not include `run_tests` in this phase.

## Validation

- Proposed new tests:
  - `tests/test_continuous_refactoring.py::test_run_agent_interactive_wraps_spawn_error_with_cause`
  - `tests/test_continuous_refactoring.py::test_run_agent_interactive_until_settled_wraps_spawn_error_with_cause`
- Keep existing interactive settle timing tests unchanged unless behavior drifts.

