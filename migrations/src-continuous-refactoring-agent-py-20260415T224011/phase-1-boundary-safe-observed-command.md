# Phase 1 — Boundary-safe `run_observed_command` in `agent.py`

## Scope (hard allowed set)

- `src/continuous_refactoring/agent.py` (only)
- `tests/test_continuous_refactoring.py` (add/update)
- `tests/test_git_branching.py` (add/update)

No other file is editable in this phase.

## Goal

Introduce boundary-level exception wrapping for observed command execution with explicit
cause chaining, without changing success semantics or log contract.

## Ready when (machine-checkable)

- All targeted tests pass:
  - `uv run pytest tests/test_continuous_refactoring.py::test_run_observed_command_writes_timestamped_logs`
  - `uv run pytest tests/test_git_branching.py::test_run_observed_command_timeout`
  - `uv run pytest tests/test_git_branching.py::test_agent_killed_when_stdout_stalled`
- `run_observed_command` returns unchanged successful `CommandCapture` payload for
  `python -c "print('hello')"` when stderr/stdout capture paths are valid.
- For a missing executable path:
  - `run_observed_command([\"/does-not-exist\"], ...)` raises `ContinuousRefactorError`
  with `__cause__` set to `FileNotFoundError`/`OSError`.

## Detailed instructions

1. In `run_observed_command`, keep behavior unchanged except for failure handling:
   - Wrap directory setup failures (`stdout_path.parent.mkdir`, `stderr_path.parent.mkdir`) in
     `ContinuousRefactorError(... ) from error`.
   - Wrap `subprocess.Popen(...)` startup failures in `ContinuousRefactorError(... ) from error`.
   - Wrap log sink open failures (`stdout_path.open`, `stderr_path.open`) in `ContinuousRefactorError(... ) from error`.
2. Preserve exact timeout and stall messages:
   - `Command timed out after {timeout}s: ...`
   - `Command killed: no output for {stuck_timeout}s: ...`
3. Do not translate successful return paths (including `<no output>` fallback writes).
4. Add/adjust tests for at least three boundaries:
   - missing command binary,
   - unwritable log directory path,
   - existing timeout/stall behavior remains string-compatible.

## Validation

- Proposed new tests:
  - `tests/test_continuous_refactoring.py::test_run_observed_command_preserves_error_cause_for_missing_binary`
  - `tests/test_continuous_refactoring.py::test_run_observed_command_preserves_error_cause_for_bad_log_dir`
  - `tests/test_git_branching.py::test_run_observed_command_timeout` (existing, unchanged)
  - `tests/test_git_branching.py::test_agent_killed_when_stdout_stalled` (existing, unchanged)
- Mechanical pass criteria:
  - all above tests pass on CI-relevant platforms,
  - `git diff --name-only` includes only files above.

