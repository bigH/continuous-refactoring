# Staged Discovery-First Split

## Strategy

Use a two-step structural migration that first makes candidate discovery explicit in place, then extracts only the stable pure core.

This avoids a blind file move. The first phase clarifies responsibilities inside `scope_expansion.py`; the second phase moves the now-obvious pure candidate builder into a new module. Selection-agent I/O stays put unless the clarified code proves it is still noisy.

Recommended destination:
- `scope_candidates.py` for candidate dataclasses, candidate construction, and discovery helpers.
- `scope_expansion.py` for bypass, selection orchestration, target conversion, and artifact writing.

This is my preferred approach if this migration is allowed more than one phase: it gets most of the structural value of extraction while reducing the chance of moving messy boundaries.

## Tradeoffs

Pros:
- Better than a one-shot split because phase 1 reveals the actual boundary before moving code.
- Preserves shippability after each phase.
- Lets tests follow behavior first, then imports second.
- Respects the taste preference for meaningful module boundaries and direct wide changes in this project.

Cons:
- More total churn than an in-place cleanup.
- Requires discipline: phase 1 must not become a full rewrite, and phase 2 must not opportunistically move selection logic.
- Two phases mean temporary duplication of thought, though not code.
- If the current module is considered "small enough," this may be more process than payoff.

## Estimated Phases

1. **Characterize and clarify in place**
   - Add missing outcome tests for candidate discovery and selection parsing.
   - Reshape `build_scope_candidates()` around an explicit internal data flow, likely with a small value object or helper for accumulated support.
   - Keep all public imports unchanged.

2. **Extract pure candidate core**
   - Move candidate dataclasses, kind literal, discovery helpers, and `build_scope_candidates()` into `scope_candidates.py`.
   - Update source and tests to import moved symbols directly.
   - Update package exports in `__init__.py`; run import checks to catch duplicate names.

3. **Trim expansion orchestration**
   - Remove leftover private helpers from `scope_expansion.py`.
   - Keep `describe_scope_candidate()` near prompt formatting only if call-site usage supports it; otherwise move it with candidates and update `prompts.py`.
   - Avoid re-export shims.

4. **Final validation**
   - Focused: `uv run pytest tests/test_scope_expansion.py tests/test_scope_selection.py tests/test_prompts_scope_selection.py tests/test_scope_loop_integration.py`.
   - Broad: `uv run pytest`.

## Risk Profile

Medium risk, with better containment than the direct extraction approach.

Main watch-outs:
- `prompts.py` currently imports `ScopeCandidate` under `TYPE_CHECKING` and uses candidate formatting helpers. Decide deliberately whether formatting is part of candidate description or prompt rendering.
- Existing tests import public symbols from `scope_expansion.py`; update them in the extraction phase instead of keeping compatibility aliases.
- Artifact JSON shape must remain stable unless the plan explicitly declares and tests a contract change.

## Best Fit

Choose this for a real migration plan. It is stronger than in-place cleanup and safer than direct extraction. The only reason not to choose it is if this migration must remain a one-commit cleanup with minimal import churn.
