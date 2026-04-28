# Phase 3: Interactive Settle Lifecycle

## Objective
Make the interactive settle path read cleanly while preserving the exact digest handshake, forced-stop sequence, and Codex terminal recovery behavior.

## Scope
- `src/continuous_refactoring/agent.py`
- `tests/test_continuous_refactoring.py`
- `tests/test_taste_interview.py` when CLI taste flows need assertion updates because they call `run_agent_interactive_until_settled()`
- `tests/test_taste_refine.py` when CLI taste flows need assertion updates because they call `run_agent_interactive_until_settled()`
- `tests/test_taste_upgrade.py` when CLI taste flows need assertion updates because they call `run_agent_interactive_until_settled()`
- `AGENTS.md` only if helper movement makes a load-bearing `agent.py` subtlety entry stale

## Instructions
1. Keep digest reading, payload fingerprinting, settle-window confirmation, terminal-state capture and restore, forced-stop behavior, and the main settle loop in one readable flow.
2. Preserve the existing settle contract exactly: `.done` must contain `sha256:<hex>` matching the content file and stay stable across the settle window before forced stop counts as success.
3. Preserve the forced-stop sequence and Codex-only recovery behavior already pinned by tests.
4. Do not widen this phase into observed-command or watchdog cleanup.
5. Update `AGENTS.md` in this phase only if the helper movement makes an `agent.py` subtlety statement inaccurate.

required_effort: medium
effort_reason: This seam mixes subprocess lifecycle, settle timing, tty state, and Codex-specific recovery; the blast radius is still local but the failure modes are sharp.

## Precondition
- Phase 2 is marked done in `migrations/src-continuous-refactoring-agent-py-20260428T041549/manifest.json`.
- Phase 1 characterization coverage for settle behavior and Codex terminal recovery is still present.

## Definition of Done
- `src/continuous_refactoring/agent.py` keeps the interactive settle helpers contiguous with `run_agent_interactive_until_settled()` and `_gracefully_stop_interactive_process()`.
- The following behaviors remain true and are proven by tests:
  - confirmed settle triggers graceful shutdown,
  - stale settle files do not count,
  - forced settled Codex sessions restore terminal state and run the Codex reset path,
  - clean exits skip the Codex reset path.
- Any taste-command test updates in this phase are limited to the `run_agent_interactive_until_settled()` integration boundary and do not broaden feature scope.
- `AGENTS.md` is updated if and only if this phase makes one of its `agent.py` subtlety notes stale.
- Validation passes and the repository remains shippable.

## Validation
- `uv run pytest tests/test_continuous_refactoring.py -k "test_gracefully_stop_interactive_process_skips_finished_process or test_gracefully_stop_interactive_process_stops_after_sigint_exit or test_gracefully_stop_interactive_process_escalates_to_sigterm or test_gracefully_stop_interactive_process_kills_after_signal_timeouts or test_run_agent_interactive_until_settled_requests_graceful_exit_after_settle or test_run_agent_interactive_until_settled_ignores_stale_settle_file or test_run_agent_interactive_until_settled_restores_terminal_state_and_codex_modes or test_run_agent_interactive_until_settled_skips_codex_reset_on_clean_exit or test_restore_codex_terminal_modes_writes_expected_escape_sequence"`
- `uv run pytest tests/test_taste_interview.py tests/test_taste_refine.py tests/test_taste_upgrade.py`
