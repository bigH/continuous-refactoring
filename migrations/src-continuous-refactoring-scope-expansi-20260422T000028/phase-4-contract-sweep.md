# Phase 4: Contract Sweep

## Objective

Lock down the final boundary and remove stale assumptions after the split.

This phase should be small. It is for contract tests, docs alignment, and dead import cleanup, not another extraction.

## Precondition

Phases 1 through 3 are complete: candidate discovery lives in `scope_candidates.py`, selection orchestration remains in `scope_expansion.py`, candidate formatting has a single final home, and the full test suite passes.

## Scope

Allowed files:

- `src/continuous_refactoring/scope_candidates.py`
- `src/continuous_refactoring/scope_expansion.py`
- `src/continuous_refactoring/prompts.py`
- `src/continuous_refactoring/__init__.py`
- `tests/test_scope_expansion.py`
- `tests/test_scope_selection.py`
- `tests/test_prompts_scope_selection.py`
- `tests/test_continuous_refactoring.py`
- `AGENTS.md` only as a repo-contract exception if the final module layout or vocabulary contradicts it

## Instructions

1. Add or tighten tests only where they protect final contracts:
   - Package import/export uniqueness still succeeds.
   - Scope expansion artifacts preserve their JSON keys and candidate field names.
   - Prompt rendering still includes candidate detail and taste sections.
   - Parser errors still translate at the module boundary through `ContinuousRefactorError`.
2. Remove stale imports, dead helper functions, and misleading comments created by the migration.
3. Check `AGENTS.md` for module layout, vocabulary, and load-bearing subtlety drift caused by this migration. Update only if needed as a repo-contract exception required by the repository instructions.
4. Do not introduce new abstractions in this phase unless they delete migration leftovers and make the boundary clearer.
5. Do not change behavior for target selection, git co-change ranking, or agent invocation.

## Definition of Done

- The final module boundary is reflected by source imports, tests, and `AGENTS.md` where applicable.
- No stale references suggest candidate discovery still lives in `scope_expansion.py`.
- No compatibility shims, dead helpers, or duplicate exports remain.
- Focused scope-selection tests and the full test suite pass.
- The repository is shippable after this phase.

## Validation

Run:

```sh
uv run pytest tests/test_scope_expansion.py tests/test_scope_selection.py tests/test_prompts_scope_selection.py tests/test_scope_loop_integration.py
uv run pytest tests/test_continuous_refactoring.py tests/test_prompts.py
uv run pytest
```
