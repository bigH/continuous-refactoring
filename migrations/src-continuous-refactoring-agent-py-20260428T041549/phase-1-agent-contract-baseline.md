# Phase 1: Agent Contract Baseline

## Objective
Pin the current public behavior of `agent.py` in tests before any structural cleanup so later phases can move helpers without guessing about behavior.

## Scope
- `tests/test_continuous_refactoring.py`
- `tests/test_claude_stream_json.py`
- `src/continuous_refactoring/agent.py` only for behavior-neutral edits required to expose already-existing outcomes to tests

## Instructions
1. Audit current coverage for command construction, unsupported backend rejection, Claude NDJSON extraction, interactive settle behavior, Codex terminal recovery, and observed-command timeout and stuck-process failures.
2. Add or tighten characterization tests only where a load-bearing behavior is not already pinned by an outcome assertion.
3. If `agent.py` must change for testability, keep the edit strictly semantics-preserving and local. No helper extraction, no helper reordering, no renames.
4. Prefer real file/process collaborators already used by the suite. Avoid mocks unless boundary isolation is already the established test shape.

required_effort: medium
effort_reason: This phase locks multiple subtle behaviors across subprocess, tty, settle, and NDJSON parsing paths before later cleanup is safe.

## Precondition
- `migrations/src-continuous-refactoring-agent-py-20260428T041549/plan.md` exists and names `approaches/agent-inplace-seams.md` as the chosen approach.
- `src/continuous_refactoring/agent.py` is still the active implementation for command building, interactive settle, and observed command execution.
- No phase in this migration is marked done in `manifest.json`.

## Definition of Done
- `tests/test_claude_stream_json.py` verifies result selection priority: last valid non-error `result`, otherwise assistant text, otherwise raw output.
- `tests/test_continuous_refactoring.py` verifies unsupported backend rejection for `build_command()`, `maybe_run_agent()`, `run_agent_interactive()`, and `run_agent_interactive_until_settled()`.
- `tests/test_continuous_refactoring.py` verifies interactive settle outcomes for:
  - graceful exit after confirmed settle,
  - stale settle file rejection,
  - Codex forced-stop terminal recovery,
  - clean exit skipping Codex reset.
- `tests/test_continuous_refactoring.py` verifies observed-command outcomes for:
  - timestamped stdout/stderr logs,
  - timeout failure without leaking full command text,
  - stuck-process failure without leaking full command text.
- Any `agent.py` edit made in this phase is solely to expose existing behavior to tests and does not reorder or rename production helpers.
- Validation passes and the repository remains shippable.

## Validation
- `uv run pytest tests/test_claude_stream_json.py`
- `uv run pytest tests/test_continuous_refactoring.py -k "test_build_command_claude_streams_json_so_watchdog_sees_progress or test_build_command_rejects_unknown_agent or test_maybe_run_agent_rejects_unknown_agent_before_path_lookup or test_run_agent_interactive_rejects_unknown_agent_before_path_lookup or test_interactive_settle_rejects_unknown_agent_before_settle_path_checks or test_run_agent_interactive_until_settled_requests_graceful_exit_after_settle or test_run_agent_interactive_until_settled_ignores_stale_settle_file or test_run_agent_interactive_until_settled_restores_terminal_state_and_codex_modes or test_run_agent_interactive_until_settled_skips_codex_reset_on_clean_exit or test_restore_codex_terminal_modes_writes_expected_escape_sequence or test_run_observed_command_writes_timestamped_logs or test_run_observed_command_timeout_hides_full_command_text or test_run_observed_command_stuck_hides_full_command_text"`
