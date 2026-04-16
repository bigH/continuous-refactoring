# Command-runtime boundary consolidation

## Strategy
- Concentrate process execution, output capture, and process termination behavior in `agent.py` so all command orchestration follows one policy and boundary failures are normalized in one place.
- Keep `loop.py` and `phases.py` focused on routing/decision logic; they should request `agent.run_observed_command` and `agent.run_tests` patterns through narrow helpers that build prompts, paths, and artifact wiring.
- Preserve current behavior; do not change rollout semantics during this migration.

## Why this is viable
- `agent.py` currently has duplicated subprocess behavior and mixed concerns (command construction, terminal restore, watch-doging, I/O formatting).
- `loop.py` and `phases.py` each re-stitch similar "run agent, check return code, run tests" flows by hand.
- This cluster already has all callers inside one local scope, so a boundary-first cleanup is mechanically verifiable.

## Tradeoffs
- Pros
  - Lower cognitive load in `loop.py` and `phases.py`.
  - Fewer places for subtle process semantics drift to hide.
  - Clearer exception translation boundary: only `agent.py` handles subprocess exceptions, callers consume stable `ContinuousRefactorError` and return codes.
- Cons
  - Medium refactor risk around interactive codex settlement semantics (`codex` terminal reset, settle path polling, forced stop path).
  - Slightly heavier API surface in `agent.py` if shared helpers are introduced.

## Estimated phases
1. **Extraction phase in `agent.py`**
   - Add internal small helpers for (a) subprocess launch options, (b) stream sink config, (c) kill/kill+timeout path.
   - Keep all public functions (`run_observed_command`, `run_tests`, `run_agent_interactive`, `run_agent_interactive_until_settled`, `maybe_run_agent`) API-compatible.
   - Add strict validation of command path and terminal state restore behavior in one place.
2. **Refactor callsites in `loop.py` and `phases.py`**
   - Introduce 1-2 narrow helper functions that encapsulate `agent -> tests -> reason` sequencing and return a local outcome tuple.
   - Remove duplicated inline patterns for commit rollback/test summary handling.
3. **Stabilization and cleanup**
   - Delete duplicate comments that describe already-obvious one-line behaviors.
   - Update docstrings to reflect domain contracts only where behavior is subtle.

## Risk profile
- Risk level: **Medium**.
- Failure modes: changed signal/termination timing, different process timeout behavior, different line buffering in interactive flows.
- Mitigation: retain existing return code contract and keep `agent`-specific settle logic untouched until parity checks pass; run all affected paths through existing smoke checks.

## Migration footprint
- `src/continuous_refactoring/agent.py`
- `src/continuous_refactoring/loop.py`
- `src/continuous_refactoring/phases.py`
