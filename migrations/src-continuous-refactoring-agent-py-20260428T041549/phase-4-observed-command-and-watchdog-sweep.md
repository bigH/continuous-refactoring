# Phase 4: Observed Command And Watchdog Sweep

## Objective
Finish the in-place cleanup by tightening the observed-command and watchdog flow, removing dead local helper paths only when proven safe, and then running the full regression suite.

## Scope
- `src/continuous_refactoring/agent.py`
- `tests/test_continuous_refactoring.py`
- `tests/test_claude_stream_json.py` only if final regression locking needs adjustment
- `tests/test_taste_interview.py`
- `tests/test_taste_refine.py`
- `tests/test_taste_upgrade.py`
- `AGENTS.md` only if final helper movement makes a load-bearing `agent.py` subtlety entry stale

## Instructions
1. Keep log writing, stream pumping, process waiting, watchdog timeout handling, and `CommandCapture` assembly in one local domain block.
2. Remove a local helper only when the phase validation proves the public behavior is unchanged.
3. Preserve the distinction between timeout and stuck-process failures, along with executable-only surfaced command names and prompt-redaction behavior.
4. Keep this phase focused on observed-command and watchdog flow. Do not use it to reshape unrelated `run_tests()` or `summarize_output()` logic beyond fallout required by local helper cleanup.
5. Update `AGENTS.md` only if the final helper layout makes a subtlety note inaccurate.

required_effort: medium
effort_reason: The cleanup is still local, but it touches watchdog failure handling and subprocess lifecycle code that can silently drift without tight verification.

## Precondition
- Phase 3 is marked done in `migrations/src-continuous-refactoring-agent-py-20260428T041549/manifest.json`.
- Phase 3 validation commands pass on the current tree.
- Phase 1 characterization tests for observed-command logging and timeout/stuck failures still pass on the current tree.

## Definition of Done
- In `src/continuous_refactoring/agent.py`, observed-command and watchdog helpers are grouped with `run_observed_command()` rather than interleaved with unrelated command or settle helpers.
- `tests/test_continuous_refactoring.py` still proves:
  - timestamped stdout/stderr log writing,
  - timeout failure without full-command leakage,
  - stuck-process failure without full-command leakage.
- No acceptance criterion in this phase depends on subjective readability claims or behavior outside the observed-command/watchdog seam, except unchanged package exports and the final regression suite.
- `AGENTS.md` is updated if and only if this phase makes one of its `agent.py` subtlety notes stale.
- Full validation, including `uv run pytest`, passes and the repository remains shippable.

## Validation
- `uv run pytest tests/test_continuous_refactoring.py -k "test_run_observed_command_writes_timestamped_logs or test_run_observed_command_timeout_hides_full_command_text or test_run_observed_command_stuck_hides_full_command_text or test_package_exports_are_stable or test_package_exports_contain_known_public_symbols"`
- `uv run pytest tests/test_claude_stream_json.py tests/test_taste_interview.py tests/test_taste_refine.py tests/test_taste_upgrade.py`
- `uv run pytest`
