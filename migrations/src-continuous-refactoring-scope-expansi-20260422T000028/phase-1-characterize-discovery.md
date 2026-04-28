# Phase 1: Characterize Discovery In Place

## Status

Human review on `2026-04-27` confirmed that the live tree already satisfies this phase and the full test suite passes. This file now records the characterization baseline that later phases must preserve.

## Objective

Keep candidate discovery explicit, well-covered, and in place while all public symbols remain in `scope_expansion.py`.

This phase reduced extraction risk before symbols move. It should remain the behavioral baseline for later phases, not a prompt to re-add the same tests.

## Precondition

The migration is still in planning or ready state, `scope_expansion.py` still defines and exports `ScopeCandidate`, `ScopeCandidateKind`, and `build_scope_candidates`, and no `src/continuous_refactoring/scope_candidates.py` module exists.

## Scope

Allowed files:

- `src/continuous_refactoring/scope_expansion.py`
- `tests/test_scope_expansion.py`
- `tests/test_scope_selection.py` only for parser gaps discovered while characterizing behavior

Do not edit package exports or production call sites in this phase.

## Instructions

1. Treat the current discovery tests in `tests/test_scope_expansion.py` as load-bearing characterization, especially:
   - an untracked seed returns only the seed candidate
   - reverse references contribute evidence and can form a local cluster
   - `max_candidates` prunes deterministically without dropping the seed candidate
   - local-only git co-change evidence does not create a noisy local sibling unless another local signal exists
2. Keep `build_scope_candidates()` readable as a small orchestration over named helpers for support accumulation, ranking, inclusion, and candidate construction.
3. Keep all public imports unchanged. Tests should still import discovery symbols from `continuous_refactoring.scope_expansion` during this phase.
4. Do not move `describe_scope_candidate()` or prompt formatting in this phase.

## Definition of Done

- Candidate discovery has explicit tests for the important discovery signals and pruning behavior.
- `build_scope_candidates()` reads as a small orchestration over named helpers rather than a mixed scoring/building block.
- No public symbol has moved out of `scope_expansion.py`.
- Existing artifact and prompt output shapes are unchanged.
- The repository is shippable after this phase.

## Validation

Run:

```sh
uv run pytest tests/test_scope_expansion.py tests/test_scope_selection.py
uv run pytest tests/test_prompts_scope_selection.py tests/test_scope_loop_integration.py
uv run pytest
```
