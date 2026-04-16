# Phase 1 — Boundary inventory and baseline lock

## Scope

Allowed scope for source edits: none.

Allowed documentation scope:
1. `migrations/src-continuous-refactoring-artifacts-py-20260415T224517/phase-1-boundary-inventory.md`
2. `migrations/src-continuous-refactoring-artifacts-py-20260415T224517/plan.md` (if needed for migration evidence updates)

## Goal

Capture baseline behavior before boundary wrapping changes so phase 2 and phase 3 can be validated against explicit evidence.

## Instructions

1. Record baseline exception boundaries by module in this phase file.
2. Record current `ContinuousRefactorError` raising and wrapping sites in `artifacts.py`, `agent.py`, `config.py`, `git.py`, `targeting.py`, `loop.py`, and `cli.py`.
3. Capture baseline expectations for command-observation and settlement flows from stable tests.
4. Add baseline entries for each listed module in this phase file.

## Ready when (machine-checkable)

1. `uv run pytest tests/test_continuous_refactoring.py::test_run_observed_command_writes_timestamped_logs`
2. `uv run pytest tests/test_git_branching.py::test_run_observed_command_timeout`
3. `uv run pytest tests/test_git_branching.py::test_agent_killed_when_stdout_stalled`
4. `uv run pytest tests/test_continuous_refactoring.py::test_run_agent_interactive_until_settled_requests_graceful_exit_after_settle`
5. `uv run pytest tests/test_continuous_refactoring.py::test_run_agent_interactive_until_settled_restores_terminal_state_and_codex_modes`
6. `uv run pytest tests/test_loop_migration_tick.py::test_6h_invariant_blocks_execution`
7. `python - <<'PY'\nfrom pathlib import Path\ntext = Path('/Users/hiren/dev/continuous-refactoring/migrations/src-continuous-refactoring-artifacts-py-20260415T224517/phase-1-boundary-inventory.md').read_text(encoding='utf-8')\nfor module in ('artifacts', 'agent', 'config', 'git', 'targeting', 'loop', 'cli'):\n    token = f'`{module}`'\n    if token not in text:\n        raise SystemExit(f'missing evidence token: {module}')\nPY`

## Validation

1. Phase 1 evidence section is updated and includes at least one baseline entry per target module.
2. All commands listed in `ready when` pass.
3. No source edits are present in phase 1.
