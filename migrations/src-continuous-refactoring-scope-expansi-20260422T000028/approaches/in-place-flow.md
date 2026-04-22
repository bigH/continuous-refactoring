# In-Place Flow Cleanup

## Strategy

Keep `src/continuous_refactoring/scope_expansion.py` as the owner of scope expansion, but reshape the existing code around clearer local flow:

1. Make candidate discovery read as a pipeline: paired files, direct references, reverse references, co-change neighbors, then candidate assembly.
2. Rename private helpers where intent is currently implicit, especially around inclusion rules and evidence aggregation.
3. Tighten tests around observed outcomes for candidate ordering, evidence de-duplication, bypass behavior, and parser errors.
4. Leave public exports and call sites untouched.

This is the safest cleanup. It accepts the current module boundary and improves readability without broadening the migration.

## Tradeoffs

Pros:
- Lowest churn; no import reshaping and minimal `__init__.py` risk.
- Keeps monkeypatch paths and direct imports stable.
- Fits the current test surface: `tests/test_scope_expansion.py`, `tests/test_scope_selection.py`, and prompt tests.
- Good match for taste where single-call abstractions are allowed if they clarify flow.

Cons:
- The module still mixes discovery, selection-agent I/O, prompt formatting glue, and artifact writing.
- Future changes to discovery rules can still accidentally touch agent/artifact concerns.
- Does not improve FQN usefulness; `scope_expansion` remains a broad bucket.

## Estimated Phases

1. **Characterize behavior**
   - Add focused tests for candidate evidence ordering, local vs cross inclusion, missing seed fallback, and artifact payload shape if absent.
   - Validation: `uv run pytest tests/test_scope_expansion.py tests/test_scope_selection.py tests/test_prompts_scope_selection.py`.

2. **Reshape private flow in place**
   - Extract small pure helpers only where they make `build_scope_candidates()` read top-down.
   - Rename weak helpers if a better domain name is obvious.
   - Preserve all public symbols in `scope_expansion.__all__`.

3. **Final cleanup**
   - Delete redundant branches exposed by the rewrite.
   - Run `uv run pytest`, plus package import smoke if tests do not cover duplicate exports clearly enough.

## Risk Profile

Low risk. Most failures would be ordinary behavior regressions in candidate ordering or evidence text, caught by existing and added tests.

Main watch-outs:
- Evidence strings are user-visible in prompts and artifacts; do not casually rename them unless tests and prompt expectations move with them.
- Candidate ordering is behavior, not presentation.
- Do not use this approach if the migration goal is explicitly to split responsibilities across modules.

## Best Fit

Choose this when the desired migration is a small, high-confidence cleanup batch. It leaves future extraction possible but does not pay the module-boundary cost now.
