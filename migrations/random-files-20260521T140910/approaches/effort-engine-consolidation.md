# Effort Engine Consolidation

## Strategy
Make `effort.py` the clear single source of truth for effort resolution rules, then prune duplicate intent in callers/tests. Drive refactor from pure-function invariants.

## Why this path
- Best when current pain is cognitive load around effort tiers/capping and phase-required behavior.
- Aligns with taste: small abstractions, strong boundaries, delete stale paths.

## Tradeoffs
- Pros: Cleaner model, easier future migration/phase scheduling changes.
- Cons: Medium chance of subtle behavioral drift if invariants are incomplete.

## Estimated phases

### Phase 1: Encode invariants as tests
- Scope: `tests/test_loop_migration_tick.py` (+ adjacent effort/migration tests if needed)
- Work:
  - Add matrix-style assertions for default/requested/required/capped combinations.
  - Verify deferred phase behavior when `required_effort` exceeds run cap.
- required_effort: `medium`

### Phase 2: Consolidate effort resolution code paths
- Scope: `src/continuous_refactoring/effort.py`
- Work:
  - Unify resolution construction paths around one internal normalization flow.
  - Keep exported API stable (`EffortBudget`, `EffortResolution`, helpers).
  - Preserve module-boundary error translation style.
- required_effort: `medium`

### Phase 3: Prune callsite complexity and dead checks
- Scope: `tests/test_prompts.py`, `src/continuous_refactoring/__main__.py`
- Work:
  - Remove stale assertions/workarounds that duplicate `effort.py` guarantees.
  - Keep only load-bearing contract tests.
- required_effort: `low`

## Risk profile
- Overall: **Medium**
- Main risks:
  - Regressing cap semantics in edge combinations.
  - Over-pruning tests that guard behavior indirectly.
- Mitigations:
  - Build exhaustive tier-order checks first.
  - Keep API and error messages stable unless explicitly reviewed.

## Best fit conditions
Pick this if maintainability of effort logic is the dominant objective.
