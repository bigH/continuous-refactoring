# Approach: Run-context rewrite using artifact-first execution pipeline

## Strategy
- Introduce a compact run-execution context object in `loop.py` that owns all per-run mutable state:
  - run artifacts
  - current target index/retry
  - branch context and head-before snapshots
  - attempt status and outcome counters.
- This context becomes the single source for when and how artifact writes happen.
- Keep rollout immediate (no canary/flags), but preserve current control flow behavior and CLI flags.

## Why this fits this migration
- The largest refactor pressure in this cluster is duplicated state mutation across `run_once` and `run_loop`:
  - status/messaging logic duplicated.
  - repeated setup/teardown patterns around retries and branch restoration.
  - artifact writes spread across both functions.
- A run-context centralizes these paths while preserving behavior.

## Estimated phases
1. `src/continuous_refactoring/loop.py`: context object + adapters
   - Add small `RunContext` dataclass (internal to module) with methods:
     - `start()`, `mark_attempt_started()`, `mark_retry()`, `mark_final_status()`.
   - Introduce helper methods for:
     - baseline prep
     - single-attempt execute flow
     - final commit/push decision
   - Keep all public signatures (`run_once`, `run_loop`) unchanged.

2. `src/continuous_refactoring/artifacts.py`: context-compatible helpers
   - Add helper methods for context transitions: `ensure_attempt`, `set_status`, `snapshot_summary`.
   - No constructor or API breaking changes.
   - Allow callers to pass context-owned run ids and final statuses directly.

3. `src/continuous_refactoring/agent.py` + `src/continuous_refactoring/git.py`
   - Move retry/test/error handling into context-owned helpers:
     - context owns commit decision (`_finalize_commit`) and workspace reset calls after failures.
   - Keep command execution semantics and timeout behavior untouched.

4. `src/continuous_refactoring/cli.py` + `src/continuous_refactoring/config.py`
   - Ensure `run-loop` error handling is context-driven:
     - CLI remains thin wrapper, no new business logic.
     - centralize taste and live-dir failures at boundary functions already close to config.

## Tradeoffs
- Pros
  - Significant simplification for future feature work in migration and retry loops.
  - Removes duplicated flow control and makes interruptions/retries explicit.
  - Good base for property-style tests on state transitions (`attempt -> retry -> commit/push/abort`).
- Cons
  - Highest blast radius of these options in currently stable, shipped control flow.
  - Easier to create subtle behavior regressions in success/failure edge cases (especially interrupt, unlimited retries, and baseline failure paths).
  - Requires broad test coverage across `run_once` and `run_loop`.

## Risk profile
- Risk: **High**
- Primary failure modes
  - different final status semantics for edge exits (`interrupted`, `baseline_failed`, `max_consecutive_failures`).
  - branch cleanup timing regressions if context lifetime is wrong.
  - stale run artifact writes after exception unwind.
- Control plan
  - phase-gated rollout with exact before/after behavior snapshots for:
    - run-once single target
    - run-loop multi-target with retry and max-consecutive-fail behavior
    - manual interrupt path.

## Outcome expectation
- Recommended only if we want to pay down structural debt now and accept broader verification overhead.
