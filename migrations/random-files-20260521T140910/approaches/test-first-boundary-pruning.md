# Test-First Boundary Pruning

## Strategy
Start from brittle/high-noise tests and workflow checks, reduce assertion noise to behavior-centric coverage, then simplify production code only where tests prove redundancy.

## Why this path
- Best when suite maintenance cost is rising and prompt/workflow assertions are noisy.
- Aligns with taste: outcome-focused testing, minimal mocks, remove dead/fallback structure.

## Tradeoffs
- Pros: Faster future iteration, clearer failures, less incidental coupling to wording.
- Cons: Requires discipline to avoid deleting guards that protect true interface contracts.

## Estimated phases

### Phase 1: Classify tests by contract vs incidental text
- Scope: `tests/test_prompts.py`, `tests/test_loop_migration_tick.py`
- Work:
  - Tag assertions as interface-critical or implementation-detail.
  - Rewrite detail-coupled checks into outcome-focused checks.
- required_effort: `low`

### Phase 2: Prune and tighten boundary checks
- Scope: `.github/workflows/pr-title.yml`, tests above
- Work:
  - Keep PR-title rule strict but simplify validation messaging/tests for clarity.
  - Ensure prompt tests verify required clauses without overfitting exact prose.
- required_effort: `medium`

### Phase 3: Opportunistic code cleanup proven by tests
- Scope: `src/continuous_refactoring/effort.py`, `src/continuous_refactoring/__main__.py`
- Work:
  - Delete tiny dead branches/helpers shown redundant by updated tests.
  - Keep module boundaries and public behavior unchanged.
- required_effort: `medium`

## Risk profile
- Overall: **Medium-Low**
- Main risks:
  - False confidence if pruning removes high-signal assertions.
  - Reviewer disagreement on what counts as contract text.
- Mitigations:
  - Keep explicit list of must-preserve interface clauses.
  - Route any contract relaxation through human review language.

## Best fit conditions
Pick this if test signal-to-noise and maintenance speed are the biggest pain.
