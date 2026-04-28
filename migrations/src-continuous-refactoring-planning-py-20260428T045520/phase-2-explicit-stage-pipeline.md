# Phase 2: Explicit Stage Pipeline

## Objective
Replace the copy-paste orchestration in `run_planning()` with a small explicit pipeline for the repeated planning stages while preserving behavior exactly.

## Scope
- `src/continuous_refactoring/planning.py`
- `tests/test_planning.py`

required_effort: medium
effort_reason: This phase changes the main planning control flow, where a subtle stage-order or stale-context regression would break migration generation without obvious local failures.

## Instructions
1. Extract the always-run planning path into a small stage spec or equivalent loop that makes stage order and stage-specific context inputs obvious at the callsite.
2. Keep the revise/review-2 branch explicit. Do not force it into the same abstraction if that would hide its special rules.
3. Preserve the current prompt-stage and artifact-label behavior:
   `revise` still runs prompt stage `expand` with stage label `revise`, and `review-2` still runs prompt stage `review` with stage label `review-2`.
4. Preserve the current context sources:
   `pick-best` gets disk-backed approach listings, `expand` gets `pick_stdout`, and review stages reread `plan.md` from disk when they execute.
5. Preserve manifest touch timing and the difference between metadata-only touches and phase rediscovery touches.
6. Do not split the module, redesign prompt composition, or broaden the phase into parser/manifest cleanup beyond what the pipeline extraction needs.

## Precondition
- Phase 1 is complete and its characterization tests are present.
- `tests/test_planning.py` currently protects stage order, revise-path behavior, context reload timing, and manifest refresh timing.
- `src/continuous_refactoring/planning.py` still uses the pre-refactor orchestration flow targeted by this migration.

## Definition of Done
- `run_planning()` uses a smaller, more explicit repeated-stage pipeline for the always-run planning path without changing observable behavior.
- The revise/review-2 branch remains explicit in the code and still aborts on findings before `final-review`.
- The same ordered stages run, with the same context sources and the same manifest touch behavior as before the refactor.
- `tests/test_planning.py` passes without weakening any Phase 1 characterization assertion.
- No new generic planning framework, speculative interface, or cross-module split is introduced.
- Full `uv run pytest` passes.
- The repository remains shippable.

## Validation
- Optional focused check while iterating: `uv run pytest tests/test_planning.py`
- Required phase gate: `uv run pytest`
