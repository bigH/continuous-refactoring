# Attempt Engine Extraction

## Strategy

Extract the retrying refactor-attempt machinery out of `loop.py` into a focused module, likely `src/continuous_refactoring/refactor_attempts.py`, while keeping top-level loop control in `loop.py`.

The new module would own:
- preserved workspace snapshots for live migrations
- single attempt execution
- validation/revert decision flow
- retry-context construction if it only serves refactor attempts

`loop.py` would keep:
- CLI entrypoints
- action budgeting and sleep behavior
- migration-first probing
- target selection and routing
- commit finalization unless a cleaner shared orchestration seam emerges during extraction

## Tradeoffs

Pros:
- Extracts the densest, most stateful branch in the file instead of nibbling around the edges.
- Gives a meaningful module boundary: “run a refactor attempt and tell me what happened.”
- Reduces duplication pressure between `run_loop()` retry flow and any future execution paths.

Cons:
- Higher churn than in-place cleanup because helpers move, imports change, and monkeypatch paths may need updates.
- Boundary choice matters: move too little and the split is fake; move too much and `loop.py` becomes a hollow shell with flow hidden elsewhere.
- `DecisionRecord` and artifact logging contracts make this seam easy to botch.

## Estimated Phases

1. Lock the attempt contract with focused tests.
   `required_effort: medium`
   - Add regression coverage for:
   - nonzero agent exit restores baseline
   - validation failure restores baseline
   - agent-requested `retry` / `abandon` / `blocked`
   - preserved live-migration workspace restore across retries

2. Extract attempt primitives into a new module.
   `required_effort: high`
   - Move `_PreservedFile`, `_PreservedWorkspaceTree`, `_preserve_workspace_tree()`, `_reset_to_source_baseline()`, `_run_refactor_attempt()`, and possibly `_retry_context()`.
   - Keep error translation at module boundaries with `from`-chained causes where new wrapping is introduced.

3. Simplify `run_loop()` around the new attempt engine.
   `required_effort: medium`
   - Replace the inline retry loop with clearer orchestration over the extracted API.
   - Keep `run_once()` separate unless the seam is obviously useful there too.

4. Optionally fold `run_once()` onto the same engine.
   `required_effort: high`
   - Only if the resulting API stays truthful and does not contort around one-shot semantics.
   - Skip this phase if it starts smelling like premature unification.

5. Validate broadly.
   `required_effort: low`
   - `uv run pytest tests/test_run_once.py tests/test_run.py tests/test_run_once_regression.py tests/test_loop_migration_tick.py`
   - `uv run pytest`

## Risk Profile

Medium.

Main risks:
- Regressing rollback/commit ownership behavior.
- Splitting responsibility for artifact logging between modules in a confusing way.
- Over-unifying `run_once()` and `run_loop()` when their semantics are similar but not the same.

Mitigations:
- Treat retry/revert behavior as the primary contract.
- Keep the extracted API outcome-based, not callback soup.
- Make `run_once()` reuse the seam only if the code gets simpler, not merely drier.

## Best Fit

Choose this when the migration should pay down the nastiest control-flow knot first, without committing to a full multi-module decomposition of all loop modes.
