# Migration Plan: `src-continuous-refactoring-agent-py-20260415T224011`

## Chosen approach

`exception-boundaries` from `approaches/exception-boundaries.md`, targeted to the
`src/continuous_refactoring` local cluster and anchored on `src/continuous_refactoring/agent.py`.

## Why this approach

It is the lowest-risk way to improve diagnosability: exception wrapping is restricted to true module boundaries, root causes are preserved via `from` chaining, and call semantics consumed by loop/phase orchestration are unchanged.

## Taste constraints to enforce

- Keep exception translation at module boundaries and preserve causes (`raise ... from error`).
- Avoid unnecessary wrappers/abstractions unless they clarify flow.
- Keep names truthful (`canary`, `upgraded`, `versionBeingRolledOut` for state; no vague temporary markers in migration state).
- Keep comments minimal.
- No runtime rollout flags/canaries for this migration; keep ship-safe behavior.
- Do not expand this into broader module reshaping.

## Phase graph (ordered, shippable, and independently verifiable)

1. `phase-1-boundary-safe-observed-command.md`
   - Edits: `agent.py` command boundary only.
   - Purpose: establish safe, causal exception wrapping for observed command execution.
   - Dependency: none.

2. `phase-2-boundary-safe-interactive.md`
   - Edits: `agent.py` interactive launch boundary only.
   - Purpose: apply the same boundary translation policy to interactive process launch.
   - Dependency: phase 1.

3. `phase-3-boundary-contract-normalization.md`
   - Edits: `agent.py` and `__init__.py` export surface only.
   - Purpose: normalize top-level boundary helpers (`maybe_run_agent`, `run_tests`) and keep contracts mechanical.
   - Dependency: phase 2.

4. `phase-4-validation-lock.md`
   - Edits: `tests/` only.
   - Purpose: lock and prove phase behavior and cross-phase invariants.
   - Dependency: phases 1–3.

## Validation strategy

- Each phase has:
  - scope-locked file list,
  - explicit `ready_when` pass/fail criteria,
  - an executable test list.
- Each phase must be mergeable independently; no changes required from later phases.
- Final validation order:
  1. phase 1 targeted checks
  2. phase 2 targeted checks
  3. phase 3 targeted checks
  4. phase 4 full migration gate

## Mechanical risk controls

- `run_tests` is owned only by phase 3 to avoid ambiguous ownership.
- No phase may edit outside its allowed file list.
- No phase may use vague acceptance gates; all gates must be codified as assertions/tests and/or exact command/result checks.

