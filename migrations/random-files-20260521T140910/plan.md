# Migration Plan: Interface-First Hardening

## Objective
Harden external contracts first (CLI effort semantics, prompt contract invariants, PR title policy behavior), then clean internals behind those contracts, with any user-visible policy shift isolated and human-review gated.

## Phase Overview
1. **Phase 1 — Boundary Contract Guardrails** (`phase-1-boundary-contract-guardrails.md`)
2. **Phase 2 — Internal Effort Resolution Cleanup** (`phase-2-internal-effort-resolution-cleanup.md`)
3. **Phase 3 — PR Title Policy Adjustment (Review-Gated)** (`phase-3-pr-title-policy-adjustment-review-gated.md`)

## Dependency Graph
```mermaid
graph TD
  P1[Phase 1: Boundary Contract Guardrails] --> P2[Phase 2: Internal Effort Resolution Cleanup]
  P1 --> P3[Phase 3: PR Title Policy Adjustment (Review-Gated)]
  P2 --> P3
```

## Why this ordering
- Phase 1 reduces regression risk by making interface expectations executable before any internal movement.
- Phase 2 then refactors internals under locked behavior so cleanup is low-risk and easy to verify.
- Phase 3 is explicitly optional and last because it can alter user-facing PR workflow semantics and should only proceed with intentional review context.

## Validation Strategy
- Baseline contract is enforced by the harness before refactoring and after each completed phase.
- Each phase also includes targeted, independently runnable checks for its own scope.
- Every phase requires the configured full validation command to pass before completion.

Validation commands used by phases:
- `uv run pytest`
- `uv run pytest tests/test_prompts.py`
- `uv run pytest tests/test_loop_migration_tick.py`
- `uv run pytest tests/test_effort.py tests/test_cli.py tests/test_run.py tests/test_run_once.py` (or nearest equivalent files if names differ)

## Interface Risk Management
- Treat CLI behavior, prompt contracts, migration-planning constraints, and PR title policy as interface surfaces.
- Any behavior change to these surfaces must be called out explicitly in phase notes and human review prompts.
- Keep compatibility-first defaults unless the phase explicitly targets a behavior change.

## Shippability bar per phase
- Repository remains releasable after each phase.
- No partial contract rewrites without matching tests.
- No silent behavior changes at interface boundaries.
