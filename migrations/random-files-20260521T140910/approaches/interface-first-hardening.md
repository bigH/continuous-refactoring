# Interface-First Hardening

## Strategy
Stabilize and clarify externally visible behavior first, then tighten internals with tests guarding contracts. Focus on behavior that users feel: CLI effort semantics, prompt contract strings, and PR-title policy.

## Why this path
- Best when regression risk at boundaries is the primary concern.
- Aligns with taste: preserve compatibility for shipped interfaces and surface behavior changes explicitly for human review.

## Tradeoffs
- Pros: Lowest risk of accidental CLI/workflow breakage; strong confidence from boundary tests.
- Cons: Some internal cleanup is deferred; may keep minor internal duplication for now.

## Estimated phases

### Phase 1: Lock boundary behavior with targeted tests
- Scope: `tests/test_prompts.py`, `tests/test_loop_migration_tick.py`, `.github/workflows/pr-title.yml`
- Work:
  - Add/adjust outcome-based tests around effort-capped migration ticking and planning gating.
  - Add prompt-contract assertions only where behavior is load-bearing (taste injection, staged/live dir constraints).
  - Validate PR title regex edge cases with fixture-like checks in workflow script block (no contract change yet).
- required_effort: `low`

### Phase 2: Refactor internals behind unchanged contracts
- Scope: `src/continuous_refactoring/effort.py`, `src/continuous_refactoring/__main__.py`
- Work:
  - Remove tiny internal repetition in effort resolution using small pure helpers.
  - Keep CLI-visible semantics identical (`low` default, `xhigh` cap, cap behavior).
  - Keep `__main__` minimal; only touch if clarity gain is concrete.
- required_effort: `medium`

### Phase 3: Optional boundary behavior adjustment (human review)
- Scope: `.github/workflows/pr-title.yml`, related tests/docs if needed
- Work:
  - If changing title policy, explicitly name user-facing impact in review prompt and migration notes.
  - Update examples/messages to match exact accepted syntax.
- required_effort: `high`

## Risk profile
- Overall: **Low**
- Main risks:
  - Hidden coupling in prompt text expectations causing brittle tests.
  - Workflow regex changes silently rejecting valid PRs.
- Mitigations:
  - Keep regex changes isolated and example-backed.
  - Prefer additive tests before edits.

## Best fit conditions
Pick this if the goal is reliability and safe incremental cleanup under active usage.
