# Approach: git-boundary-minimal

## Strategy
Keep this migration tight: modernize only `src/continuous_refactoring/git.py` and the immediate call contracts in `src/continuous_refactoring/loop.py` that consume it. The goal is cleaner fault signaling without changing orchestration behavior.

- Preserve existing API shape (`run_command`, `prepare_run_branch`, etc.).
- Add explicit exception chaining at the git module boundary (`raise ContinuousRefactorError(...) from exc`) for any caught subprocess/runtime failures in helper paths.
- Normalize message shape with command context + captured stdout/stderr, but only add context, never reinterpret meaning.
- Keep branch-selection and branch-name behavior untouched unless evidence in this migration proves a correctness bug.

## Tradeoffs
- Pros: lowest churn, fastest path to shippable, tightly scoped blast radius, easier rollback if any behavior wobble appears.
- Cons: leaves duplicated boundary behavior in `config.py`/`phases.py` untouched; this may still be future cleanup.

## Estimated phases
1. **Phase 1 — Baseline lock-in**
   - No source edits.
   - Snapshot current git boundary behavior by mapping calls in `loop.py` and `phases.py` that pass through `ContinuousRefactorError` from git operations.
   - Capture baseline expectations from `tests/test_git_branching.py` and branch-related paths in loop tests.

2. **Phase 2 — Git boundary hardening**
   - Edit `src/continuous_refactoring/git.py` only.
   - Add cause-preserving wraps in:
     - `run_command` around `subprocess.run` failures.
     - `get_head_sha`/`detect_main_branch`/`_git_head_ref_exists` where external command failures currently lose original signal.
   - Keep existing status transitions and return types unchanged.

3. **Phase 3 — Loop boundary hygiene**
   - Edit `src/continuous_refactoring/loop.py` where git calls are caught and wrapped.
   - Keep `final_status` labels stable and only convert wraps to causal forms (`from error`).

4. **Phase 4 — Verification and lock**
   - Update/extend tests for two outcomes:
     - cause-chain retention for wrapped git failures.
     - unchanged branch/migrate control flow.
   - Suggested commands:
     - `uv run pytest tests/test_git_branching.py`
     - `uv run pytest tests/test_loop_migration_tick.py tests/test_run.py tests/test_run_once.py`

## Risk profile
- Risk: **low**.
- Regression risk: mostly string-shape and exception-flow assertions; no user-facing API changes.
- Rollout risk: low; this is straightforward migration-internal cleanup and respects broad blast-radius preference.
