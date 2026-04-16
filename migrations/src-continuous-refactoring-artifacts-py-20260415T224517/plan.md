# Migration Plan: `src-continuous-refactoring-artifacts-py-20260415T224517`

## Chosen approach

`exception-boundary-hardening` from `approaches/exception-boundary-hardening.md`.

## Design goal

Keep behavior stable, keep call flow stable, and add root-preserving exception chains at real module boundaries for:
1. `artifacts.py`
2. `agent.py`
3. `config.py`
4. `git.py`
5. `targeting.py`
6. `loop.py`
7. `cli.py`

This plan avoids rollout flags, avoids speculative abstractions, and preserves migration status names (`completed`, `failed`, `interrupted`, etc.).

## Phase order

1. `phase-1-boundary-inventory.md`
   - Dependencies: none
   - Risk goal: make baseline behavior explicit before edits.
2. `phase-2-core-boundary-hardening.md`
   - Dependencies: phase 1
   - Risk goal: add causal chaining only in core owner modules.
3. `phase-3-loop-cli-contract-alignment.md`
   - Dependencies: phases 1 and 2
   - Risk goal: remove duplicate wrapping and align user/runner error contracts.
4. `phase-4-validation-lock.md`
   - Dependencies: phases 1, 2, and 3
   - Risk goal: lock causal behavior and artifact/write contracts with test assertions.

## Shippable invariant per phase

Each phase must satisfy:
1. All pre-declared file-scope boundaries are respected.
2. Commands listed in each phase `ready_when` block pass in the phase-local checkout state.
3. No file outside that phase scope is required to execute the phase.
4. Existing success outcomes stay stable for `run_loop`, `run_once`, `run_observed_command`, and `run_agent_interactive_until_settled`.

## Validation stack

1. Phase 1 validates pre-change behavior and failure surface shape.
2. Phase 2 validates boundary ownership and causal chain propagation where translations begin.
3. Phase 3 validates one-time boundary translation in orchestration/CLI entry layers.
4. Phase 4 validates complete migration lock, including `__cause__` and artifacts persistence invariants.

## Global validation controls

1. All checks use pytest commands from the project test environment.
2. All phases are machine-checkable and can be executed independently.
3. If a phase is not shippable, execution stops and later phases are not started.
