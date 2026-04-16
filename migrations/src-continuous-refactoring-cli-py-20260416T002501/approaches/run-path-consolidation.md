# Approach: Target execution path consolidation

## Strategy
- Consolidate the two user entrypaths (`run_once` and `run_loop`) behind a shared, explicit execution flow.
- Extract the repeated orchestration into narrow internal helpers in `loop.py`:
  - preflight setup (`prepare_run_branch`, baseline checks, target selection)
  - single target attempt execution (`agent -> tests -> revert/commit -> push`)
  - route outcomes (`success`, `failed`, `not-routed`) and final status mapping.
- Keep all behavior and statuses identical, only make flow shape denser and easier to reason about.
- Use one local context object (pure data, short lifecycle) for per-run state instead of passing half a dozen locals.

## Why this migration is viable
- `run_once` and `run_loop` duplicate substantial orchestration with minor deltas.
- The duplicate structure increases drift risk and makes future change sets around retry and migration routing expensive.
- This cluster is exactly a good target for readability-driven consolidation because flow is local and testable.

## Tradeoffs
- Pros
  - Immediate reduction of duplicated branches and branch-state drift.
  - Easier to add/validate additional outcomes later (`route` + `refactor` + `plan` + `migration`).
  - Better long-term maintainability of `max_attempts`, retries, and failure counters.
- Cons
  - Highest blast radius among options in this migration due intertwined control flow.
  - Risk of subtle behavioral mismatch around `retry` counters, `max_consecutive_failures`, and branch restoration.
  - Longer first phase before visible progress.

## Estimated phases
1. **Attempt context abstraction**
   - Add a compact internal dataclass in `loop.py` (target index, retry index, head-before, commit prefix, model/effort pair, artifact dir paths).
   - Make orchestration helpers consume and return immutable outcome objects.
2. **Single-attempt executor**
   - Extract the common block that currently lives in both `run_once` and `run_loop` into one helper: reset/discard, run agent, run tests, revert on fail, finalize commit/push on success.
   - Keep attempt semantics identical, including where `fix_amendment` is attached in retries.
3. **Entrypoint adapters**
   - Rebuild `run_once` as a constrained adapter around the same executor with single-target setup.
   - Rebuild `run_loop` as the multi-target driver that loops and invokes helper outcomes.
4. **Route boundary pass**
   - Keep routing (`_route_and_run`) untouched except for cleaner status flow into shared executor.

## Risk profile
- Risk level: High.
- Main risk: semantic regressions in control-flow edges (baseline failure, interruption, unlimited retries, migration-first routing).
- Control plan: execute in strict phases and preserve status output order so behavior can be side-by-side compared before/after.

## Migration footprint
- `src/continuous_refactoring/loop.py`
