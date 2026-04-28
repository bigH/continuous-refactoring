# Phase 2: Command And Backend Seams

## Objective
Reorder and tighten the command-construction and backend-validation path so those helpers form one readable block at the top of `agent.py` without changing behavior.

## Scope
- `src/continuous_refactoring/agent.py`
- `tests/test_continuous_refactoring.py` when command-path expectations need adjustment after helper movement
- `tests/test_claude_stream_json.py` only if non-interactive Claude command wiring changes test setup, not behavior

## Instructions
1. Keep `_require_supported_agent`, command builders, interactive command selection, and `maybe_run_agent()` in one local flow.
2. Preserve backend-specific truth:
  - unsupported backend errors still surface at the same public boundary,
  - Claude still uses the `stream-json` command shape,
  - Codex non-interactive flow still requires `last_message_path`.
3. Introduce only small typed helpers that remove repetitive branching or plumbing. If a helper hides behavior, delete it.
4. Do not change settle lifecycle helpers, watchdog helpers, or observed-command behavior in this phase except for unavoidable call-site fallout from local reordering.

required_effort: low
effort_reason: This is a local readability cleanup after Phase 1 has pinned the command-path contracts.

## Precondition
- Phase 1 is marked done in `migrations/src-continuous-refactoring-agent-py-20260428T041549/manifest.json`.
- Phase 1 validation commands pass on the current tree.
- `src/continuous_refactoring/agent.py` still contains the existing settle and observed-command implementations that later phases will clean up.

## Definition of Done
- In `src/continuous_refactoring/agent.py`, command/backend helper ordering places backend validation and command assembly before the call sites that consume them.
- `build_command()` still emits Claude `stream-json` commands and still rejects unknown backends with `ContinuousRefactorError`.
- `maybe_run_agent()`, `run_agent_interactive()`, and `run_agent_interactive_until_settled()` still reject unsupported backends before agent-path lookup or settle-path work begins.
- No tests or code in this phase change settle-handshake behavior, Codex reset behavior, watchdog behavior, or observed-command error contracts.
- Validation passes and the repository remains shippable.

## Validation
- `uv run pytest tests/test_continuous_refactoring.py -k "test_build_command_claude_streams_json_so_watchdog_sees_progress or test_build_command_rejects_unknown_agent or test_maybe_run_agent_rejects_unknown_agent_before_path_lookup or test_run_agent_interactive_rejects_unknown_agent_before_path_lookup or test_interactive_settle_rejects_unknown_agent_before_settle_path_checks"`
- `uv run pytest tests/test_claude_stream_json.py`
