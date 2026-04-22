# Phase 1: Characterize Discovery In Place

## Objective

Make candidate discovery behavior explicit and well-covered while all public symbols remain in `scope_expansion.py`.

This phase reduces extraction risk. It should clarify the data flow around evidence, scores, ranking, and candidate construction without changing import paths.

## Precondition

The migration is still in planning or ready state, `scope_expansion.py` still defines and exports `ScopeCandidate`, `ScopeCandidateKind`, and `build_scope_candidates`, and no `src/continuous_refactoring/scope_candidates.py` module exists.

## Scope

Allowed files:

- `src/continuous_refactoring/scope_expansion.py`
- `tests/test_scope_expansion.py`
- `tests/test_scope_selection.py` only for parser gaps discovered while characterizing behavior

Do not edit package exports or production call sites in this phase.

## Instructions

1. Add focused outcome tests for discovery behavior that is currently implicit. Prefer tests that build small real git repos through existing test helpers.
2. Cover at least these cases if missing:
   - An untracked seed returns only the seed candidate.
   - Reverse references contribute evidence and can produce a local cluster when appropriate.
   - `max_candidates` prunes deterministically without dropping the seed candidate.
   - Local-only git co-change evidence does not create a noisy local sibling unless another local signal exists.
3. Reshape `build_scope_candidates()` in place so the flow is easier to read:
   - Keep score/support accumulation separate from candidate construction.
   - Use a small frozen value object only if it makes the discovery flow clearer.
   - Keep helper names domain-specific; avoid generic names like `data`, `temp`, or `thing`.
4. Keep all public imports unchanged. Tests should still import discovery symbols from `continuous_refactoring.scope_expansion`.
5. Do not move `describe_scope_candidate()` or prompt formatting in this phase.

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
