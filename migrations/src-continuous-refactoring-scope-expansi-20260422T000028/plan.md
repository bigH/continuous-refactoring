# Scope Expansion Candidate Discovery Migration

## Goal

Split `scope_expansion.py` along the real domain boundary:

- `scope_candidates.py` owns candidate data, discovery, evidence, scoring, ranking, and validation-surface inference.
- `scope_expansion.py` owns bypass decisions, selection-agent orchestration, target conversion, and artifact writing.
- Prompt formatting stays in `prompts.py` when it is presentation-oriented.

Do this in stages. Phase 1 proves and clarifies the boundary in place. Only after that should symbols move.

## Non-Goals

- Do not change the scope-selection artifact JSON contract unless a phase explicitly adds and verifies that contract change.
- Do not keep compatibility aliases or re-export shims from `scope_expansion.py`.
- Do not move selection-agent I/O into the candidate module.
- Do not introduce runtime dependencies.
- Do not refactor unrelated routing, agent, artifact, targeting, or git behavior.

## Scope Notes

The selected local cluster includes:

- `src/continuous_refactoring/scope_expansion.py`
- `tests/test_scope_expansion.py`
- `src/continuous_refactoring/prompts.py`
- `src/continuous_refactoring/__init__.py`
- `src/continuous_refactoring/targeting.py`
- `src/continuous_refactoring/agent.py`
- `src/continuous_refactoring/artifacts.py`
- `src/continuous_refactoring/git.py`

This plan also adds `src/continuous_refactoring/routing_pipeline.py` to the migration scope because it directly imports `build_scope_candidates`, `describe_scope_candidate`, and the scope expansion orchestration functions from `continuous_refactoring.scope_expansion`. Phase 2 and Phase 3 may update only those imports and directly related call sites in `routing_pipeline.py`; they must not refactor routing behavior.

`AGENTS.md` is a repo-contract exception, not fuzzy migration scope. The repo requires updating it in the same commit as code that contradicts its module-layout guidance, so Phase 2 or Phase 4 may touch `AGENTS.md` only to keep that contract true after adding `scope_candidates.py`.

## Phases

1. `characterize-discovery` - Add missing outcome tests and clarify candidate discovery inside `scope_expansion.py` without moving public imports.
2. `extract-scope-candidates` - Move the stable discovery core into `scope_candidates.py`, update all direct imports, and update package exports.
3. `trim-expansion-orchestration` - Finish the boundary by moving presentation-only candidate description to `prompts.py` and removing leftover candidate helpers from `scope_expansion.py`.
4. `contract-sweep` - Lock down import, artifact, and prompt contracts after the split; update repo guidance if the new module layout requires it.

## Dependencies

Phase 1 blocks every later phase. It creates the test net and clarifies the internal shape before symbols move.

Phase 2 depends on Phase 1. It must not start while discovery behavior is still under-characterized.

Phase 3 depends on Phase 2. Presentation cleanup only makes sense after candidate ownership has moved.

Phase 4 depends on Phases 2 and 3. It verifies the final public surface and removes stale guidance after the structural work is complete.

```mermaid
flowchart TD
    P1["1. characterize-discovery"]
    P2["2. extract-scope-candidates"]
    P3["3. trim-expansion-orchestration"]
    P4["4. contract-sweep"]

    P1 --> P2 --> P3 --> P4
```

## Agent Assignments

- Phase 1: Artisan implements tests and in-place cleanup; Test Maven reviews behavior coverage.
- Phase 2: Artisan performs the move; Critic reviews import surface and shim avoidance.
- Phase 3: Artisan trims orchestration; Critic reviews module boundaries and FQN clarity.
- Phase 4: Test Maven owns verification; Critic checks docs and public contracts.

## Validation Strategy

Every phase must run focused tests before full tests:

- Focused discovery and selection: `uv run pytest tests/test_scope_expansion.py tests/test_scope_selection.py tests/test_prompts_scope_selection.py tests/test_scope_loop_integration.py`
- Import/package smoke: `uv run pytest tests/test_continuous_refactoring.py tests/test_prompts.py`
- Full gate: `uv run pytest`

Use broader validation whenever a phase updates package exports, prompt formatting, or routing imports.

## Risk Notes

- `src/continuous_refactoring/__init__.py` rejects duplicate exported symbols at import time. After Phase 2, moved symbols must live in exactly one module's `__all__`.
- `prompts.py` currently type-checks `ScopeCandidate` from `scope_expansion.py`. After extraction, that type should come from `scope_candidates.py`.
- `routing_pipeline.py` should import candidate discovery from `scope_candidates.py` and selection/orchestration behavior from `scope_expansion.py`.
- `AGENTS.md` says the source tree is flat with roughly 13 modules. Adding `scope_candidates.py` changes that guidance; update it in the same phase that adds the module as a repo-contract exception.
- Keep artifact payload keys and candidate field names stable: `target`, `bypass_reason`, `candidates`, `selection`, and the dataclass field names.
