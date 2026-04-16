# Approach: cluster-boundary-contract

## Strategy
Treat the migration as a cohesive boundary-contract cleanup across `git.py` plus the modules that already own validation and orchestration semantics (`loop.py`, `phases.py`, `config.py`, `targeting.py`). Keep behavior stable but stop re-wrapping the same exception at multiple layers.

- Make `git.py` the clear boundary for subprocess/git-local failures.
- Make `loop.py` and `phases.py` wrap only orchestration outcomes, with preserved causes from lower modules.
- In `config.py` and `targeting.py`, keep parse/load validation close to source semantics and ensure raised `ContinuousRefactorError`s include root causes for parse and filesystem boundaries.
- Respect taste rule: translate only at true module boundaries and keep real rollout state names intact.

## Tradeoffs
- Pros: cleaner long-term diagnosability, stronger contract consistency, fewer surprise rewrites across error paths.
- Cons: broader edit surface, more places where tests that assert messages need adjustment, slightly longer validation cycle.

## Estimated phases
1. **Phase 1 — Boundary mapping**
   - Static inventory of all `ContinuousRefactorError` raises in the migration cluster.
   - Classify each by ownership: command boundary, parsing boundary, orchestration boundary.

2. **Phase 2 — Leaf boundaries first**
   - Edit `src/continuous_refactoring/git.py` and `src/continuous_refactoring/config.py`.
   - Add causal chaining and keep translated messages additive.
   - Ensure no semantic behavior changes in `run_command`, manifest/version helpers, and path resolution.

3. **Phase 3 — Orchestration boundaries**
   - Edit `src/continuous_refactoring/loop.py`, `src/continuous_refactoring/phases.py`, `src/continuous_refactoring/targeting.py`.
   - Remove duplicate wrapping, preserve root causes, keep status machine (`completed`, `baseline_failed`, `migration_failed`, etc.) unchanged.

4. **Phase 4 — Prompt-surface guardrails**
   - Edit `src/continuous_refactoring/prompts.py` only if any existing template now misdirects scope (status wording/contract naming only).
   - Keep prompt output stable unless migration-specific clarity improves failure triage.

5. **Phase 5 — Test lock**
   - Add cause-chain checks for at least one representative path in each boundary layer.
   - Run cluster validation for touched modules.
   - Suggested commands:
     - `uv run pytest tests/test_git_branching.py`
     - `uv run pytest tests/test_config.py tests/test_loop_migration_tick.py tests/test_run.py tests/test_run_once.py`
     - `uv run pytest tests/test_continuous_refactoring.py::test_run_observed_command_timeout`

## Risk profile
- Risk: **medium**.
- Regression risk: moderate where error paths/exception strings are asserted; control-flow risk low because branch names and migration outcomes remain unchanged.
- Rollout risk: acceptable only because this is a shippable codebase with no speculative abstractions.
