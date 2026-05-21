# Delete Dead Paths Then Re-prove

## Strategy
Aggressively remove fallback/legacy code in random-targeted files, then re-prove required behavior with concise tests and boundary checks.

## Why this path
- Matches taste preference for deleting unused paths in non-shipped internals.
- Delivers the biggest readability gain per line changed when dead code exists.

## Tradeoffs
- Pros: Strong simplification; future maintenance gets easier quickly.
- Cons: Highest chance of exposing implicit dependencies that looked unused.

## Estimated phases

### Phase 1: Dead-path inventory and dependency check
- Scope: random-targeted files plus direct callers/tests
- Work:
  - Identify branches/helpers/tables with no live call path.
  - Confirm no external contract depends on them.
- required_effort: `medium`

### Phase 2: Removal pass with boundary-preserving errors
- Scope: selected source files
- Work:
  - Delete dead flags/shims/branches outright.
  - Preserve or improve exception nesting only at module boundaries.
- required_effort: `high`

### Phase 3: Re-proof via focused regression + integration checks
- Scope: relevant `tests/test_*.py`
- Work:
  - Add/update tests for post-deletion behavior and side effects.
  - Confirm full pytest gate remains green.
- required_effort: `medium`

## Risk profile
- Overall: **Medium-High**
- Main risks:
  - Removing code that encodes undocumented edge behavior.
  - Larger diff in mixed-scope random files.
- Mitigations:
  - Require explicit evidence of deadness before deletion.
  - Keep deletions and proof tests in the same phase boundary.

## Best fit conditions
Pick this when maintainability pain is from stale fallback logic and the team accepts moderate refactor risk.
