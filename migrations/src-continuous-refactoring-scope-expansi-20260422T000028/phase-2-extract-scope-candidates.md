# Phase 2: Extract Scope Candidates

## Objective

Move pure candidate discovery into a domain-focused module with meaningful FQNs, and make the test ownership match the module split.

`continuous_refactoring.scope_candidates` should become the home for candidate data and discovery. `scope_expansion.py` should continue to handle selection and artifacts.

## Precondition

Phase 1 is complete: discovery behavior is covered by focused tests, `build_scope_candidates()` has a clear internal discovery flow, and all tests pass with the public symbols still exported from `scope_expansion.py`.

## Scope

Allowed files:

- `src/continuous_refactoring/scope_candidates.py`
- `src/continuous_refactoring/scope_expansion.py`
- `src/continuous_refactoring/__init__.py`
- `src/continuous_refactoring/prompts.py`
- `src/continuous_refactoring/routing_pipeline.py`
- `tests/test_scope_candidates.py`
- `tests/test_scope_expansion.py`
- `tests/test_prompts_scope_selection.py`
- `tests/test_scope_loop_integration.py` if import patch targets require it
- `tests/test_continuous_refactoring.py` if package export expectations need coverage
- `AGENTS.md` only as a repo-contract exception if module layout guidance changes

`src/continuous_refactoring/routing_pipeline.py` is included by explicit scope correction because it directly imports moved scope candidate symbols. Update only imports and directly related call sites there.

## Instructions

1. Create `src/continuous_refactoring/scope_candidates.py`.
2. Create `tests/test_scope_candidates.py` as the canonical home for pure discovery behavior. Move or rewrite the characterization coverage there so `tests/test_scope_expansion.py` can narrow to the expansion boundary.
3. Move these symbols into the new module:
   - `ScopeCandidateKind`
   - `ScopeCandidate`
   - `build_scope_candidates`
   - private discovery helpers used only by candidate construction
4. Keep these symbols in `scope_expansion.py`:
   - `ScopeSelection`
   - `scope_expansion_bypass_reason`
   - `parse_scope_selection`
   - `scope_candidate_to_target`
   - `select_scope_candidate`
   - `write_scope_expansion_artifacts`
   - `describe_scope_candidate` until Phase 3 moves it to `prompts.py`
5. Update imports directly at every call site. Do not add compatibility aliases or re-export shims from `scope_expansion.py`.
6. Update `src/continuous_refactoring/__init__.py` so `scope_candidates` participates in package re-export uniqueness checks.
7. Update tests and type-checking imports so moved symbols and canonical discovery coverage come from `continuous_refactoring.scope_candidates`.
8. If `AGENTS.md` still describes the old module count or read-first shape, update it in this phase as a repo-contract exception required by the repository instructions.

## Definition of Done

- `continuous_refactoring.scope_candidates.ScopeCandidate` and `build_scope_candidates` are the canonical imports.
- `tests/test_scope_candidates.py` is the canonical discovery test file, and `tests/test_scope_expansion.py` covers bypass, selection, target conversion, and artifact writing behavior.
- `scope_expansion.py` no longer defines or exports candidate data/discovery symbols.
- No moved symbol is re-exported from `scope_expansion.py`.
- Package import succeeds and duplicate export checks still protect the public surface.
- Existing scope expansion behavior, selection behavior, prompt formatting, and artifact JSON shape remain unchanged.
- The repository is shippable after this phase.

## Validation

Run:

```sh
uv run pytest tests/test_scope_candidates.py tests/test_scope_expansion.py tests/test_prompts_scope_selection.py tests/test_scope_loop_integration.py
uv run pytest tests/test_continuous_refactoring.py tests/test_prompts.py
uv run pytest
```
