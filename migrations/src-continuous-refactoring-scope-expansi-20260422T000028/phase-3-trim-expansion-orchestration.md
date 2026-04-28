# Phase 3: Trim Expansion Orchestration

## Objective

Finish the boundary cleanup after extraction.

`scope_expansion.py` should be about bypass, selection, target conversion, and artifact writing. Human review approved candidate presentation living with prompt formatting, so `describe_scope_candidate()` should move to `prompts.py`.

## Precondition

Phase 2 is complete: `scope_candidates.py` owns candidate data and discovery, moved symbols are imported directly from their new module, no compatibility shims exist in `scope_expansion.py`, and the full test suite passes.

## Scope

Allowed files:

- `src/continuous_refactoring/scope_expansion.py`
- `src/continuous_refactoring/prompts.py`
- `src/continuous_refactoring/routing_pipeline.py`
- `src/continuous_refactoring/__init__.py`
- `tests/test_prompts_scope_selection.py`
- `tests/test_scope_expansion.py`
- `tests/test_scope_loop_integration.py`
- `tests/test_prompts.py`

`src/continuous_refactoring/routing_pipeline.py` is included by explicit scope correction because it directly consumes candidate discovery and candidate-description output from the scope expansion boundary. Update only imports and directly related planning-context call sites there.

## Instructions

1. Move `describe_scope_candidate()` to `prompts.py`. Keep its text behavior stable unless a test proves a change is required.
2. Update `routing_pipeline.py` to import candidate formatting from `prompts.py`.
3. Remove now-unused imports and helper dependencies from `scope_expansion.py`.
4. Keep prompt text behavior stable. If formatting changes are unavoidable, make them smaller and verify them with outcome tests.
5. Keep `__all__` accurate in every touched module.
6. Do not move selection parsing, agent invocation, artifact writing, or target conversion.

## Definition of Done

- `scope_expansion.py` contains no candidate discovery helpers and no prompt-formatting helpers.
- `prompts.py` owns both `scope_candidate_detail_lines()` and `describe_scope_candidate()`.
- Candidate description formatting has one canonical public home with direct imports from call sites.
- `prompts.py` has no runtime circular import with candidate or expansion modules.
- Scope selection prompts still include candidate files, cluster labels, evidence, validation surfaces, and taste.
- The repository is shippable after this phase.

## Validation

Run:

```sh
uv run pytest tests/test_prompts_scope_selection.py tests/test_prompts.py
uv run pytest tests/test_scope_candidates.py tests/test_scope_expansion.py tests/test_scope_loop_integration.py
uv run pytest
```
