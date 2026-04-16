# Approach: shared-command-runners

## Strategy
Introduce a single shared command-execution contract in `agent.py` and drive loop/phase command calls through it, while keeping orchestration logic where it lives.

The contract is explicit and tiny:
- `run_command_once`: process launch + stream capture + timeout + stall watchdog + log persistence (already in `run_observed_command`).
- `run_validating_command`: wraps `run_command_once` for common return-code checks in loop/planning/phase call sites.

Keep domain rules in `loop.py` and `phases.py`; do not move orchestration logic out of those modules.

## Why this fits
The cluster has three execution consumers (`run_observed_command`, `run_loop`, and `execute_phase`) doing similar setup patterns and log directory layout assumptions. Unifying this path reduces duplication and makes future command behavior changes safer.

## Tradeoffs
1. Pros
   - Reduced drift between migration and non-migration paths.
   - Single place for timeout/stall/IO behavior makes future hardening easier.
   - Better fit for taste around "abstraction for readability/flow".
2. Cons
   - Moderate refactor surface: requires touching `loop.py`, `phases.py`, maybe `test_*` call assertions.
   - Potentially wider behavioral coupling if names/paths are over-normalized.
   - Higher chance of brittle snapshot tests in command output-related assertions.

## Estimated phases
1. Phase 0 — compatibility capture
   - Snapshot current command semantics with regression tests around `run_once`, `_route_and_run`, and phase execution.
2. Phase 1 — abstraction extraction in `agent.py`
   - Extract common process policy from existing functions into reusable internals (no API expansion).
   - Add type-safe helpers and doc-level comments only where the contract boundary is non-obvious.
3. Phase 2 — migrate consumers
   - Rewrite command invocations in `loop.py` and `phases.py` to use the contract.
   - Preserve existing path naming (`agent.stdout.log`, `tests.stdout.log`) at call sites.
4. Phase 3 — tighten and lock
   - Add tests for timeout + stall outcomes from the shared path.
   - Ensure migration manifests remain unchanged in phase-ready/execute behavior.

## Risk profile
- Risk level: medium.
- Operational risk: medium during the migration window because command execution is central to all refactor and migration flows.
- Containment: medium to high if phase-by-phase commit checkpoints are added and each phase must pass regression subset before moving on.

