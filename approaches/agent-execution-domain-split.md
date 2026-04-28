# Approach: Execution-Domain Split

## Strategy
- Split `agent.py` by execution model rather than by backend.
- Proposed modules:
  - `src/continuous_refactoring/agent_commands.py` for agent command construction and support checks,
  - `src/continuous_refactoring/agent_interactive.py` for settle protocol, signal escalation, terminal reset, and TTY handling,
  - `src/continuous_refactoring/agent_observed.py` for subprocess capture, watchdog behavior, timestamped logs, and test execution,
  - `src/continuous_refactoring/agent.py` as a thin public facade.
- Keep public function names stable: `build_command`, `maybe_run_agent`, `run_agent_interactive`, `run_agent_interactive_until_settled`, `run_observed_command`, `run_tests`, `summarize_output`.

## Tradeoffs
- Cleanest long-term structure. The boundaries match how callers think about the module.
- Makes the load-bearing settle protocol and watchdog code easier to review in isolation.
- Highest churn of the options here. More files, more imports, more chances to nick a subtle invariant.
- Adds a facade module, which is justified only if we believe `agent.py` will keep evolving.

## Estimated phases
1. Extract `agent_commands.py` and move backend validation plus command builders first.
   - `required_effort`: `medium`
2. Extract `agent_observed.py` for command capture, watchdog, and `run_tests`.
   - `required_effort`: `medium`
3. Extract `agent_interactive.py` for settle protocol, terminal state handling, and forced Codex reset.
   - `required_effort`: `high`
4. Collapse `agent.py` into a thin facade with direct imports and no compatibility shims beyond those imports.
   - `required_effort`: `low`
5. Rebalance tests around the new module boundaries and run full pytest.
   - `required_effort`: `medium`

## Risk profile
- Technical risk: medium-high
- Blast radius: high
- Failure modes:
  - Import layering mistakes around `ContinuousRefactorError`, `CommandCapture`, and shared helpers.
  - Behavioral regressions in the settle handshake or watchdog teardown because lifecycle code moved wholesale.
  - Package export collisions or stale imports if the facade and implementation modules drift.

## Best when
- We want the migration to end with a durable structure, not just a neater big file.
- We can afford a higher-churn refactor in exchange for clearer review surfaces later.
