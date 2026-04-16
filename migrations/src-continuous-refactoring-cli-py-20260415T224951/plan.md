# Migration Plan: `src-continuous-refactoring-cli-py-20260415T224951`

## Chosen approach

`error-boundary-contract` from `approaches/error-boundary-contract.md`.

## Chosen scope

`src/continuous_refactoring/*` local cluster, with these target files:

- `src/continuous_refactoring/agent.py`
- `src/continuous_refactoring/prompts.py`
- `src/continuous_refactoring/loop.py`
- `src/continuous_refactoring/artifacts.py`
- `src/continuous_refactoring/__init__.py`
- `src/continuous_refactoring/config.py`
- `src/continuous_refactoring/cli.py`
- `src/continuous_refactoring/__main__.py`

## Migration goal

Own error translation at explicit module boundaries, use `raise ... from error` for cause propagation, and preserve success-path behavior at all phases. Keep CLI user outputs and exit codes stable unless migration plan explicitly says otherwise.

## Phase graph and dependencies

1. `phase-1-boundary-contract-audit.md`  
   - Dependency: none.
2. `phase-2-leaf-module-boundary-wrapping.md`  
   - Dependency: phase 1.
3. `phase-3-loop-boundary-contract.md`  
   - Dependency: phase 2.
4. `phase-4-cli-boundary-contract-and-exit-paths.md`  
   - Dependency: phase 3.

## Validation strategy

1. Each phase has a scope lock, deterministic `ready_when`, and executable validation steps.
2. Each phase may land independently without requiring later phase files.
3. Validation always covers command outcome and causal chain retention where boundary wrapping is part of that phase.
4. No phase may modify `tests/*` or files outside the chosen cluster.

## Phase ordering policy

The order is dependency-reducing:

- phase 1 creates a complete boundary map.
- phase 2 applies leaf boundary wrapping to reduce risk of hidden exceptions in loop/cli.
- phase 3 normalizes loop-owned contract boundaries after leaf behavior is stable.
- phase 4 centralizes CLI boundary translation and verifies stable exit behavior.

