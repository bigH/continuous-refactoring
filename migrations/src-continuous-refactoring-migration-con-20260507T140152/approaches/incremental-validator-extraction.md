# Incremental Validator Extraction

## Strategy
Keep behavior stable while extracting `migration_consistency.py` into a small validation pipeline with explicit rule groups (directory visibility, manifest integrity, phase file integrity, phase doc contract). Preserve exported symbols and finding codes.

## Why this approach
- Lowest interface risk across `migration_tick.py`, `migration_cli.py`, `review_cli.py`, `planning.py`, and `planning_publish.py`.
- Improves readability without changing CLI behavior or migration manifest semantics.
- Easy to stop at any phase with shippable intermediate states.

## Tradeoffs
- Leaves some duplication in mode/status gating unless we do later consolidation.
- Gains clarity more than capability.
- Slightly more helpers means more function boundaries to maintain.

## Estimated phases
1. Baseline + characterization tests (`required_effort: low`)
- Expand `tests/test_migration_consistency.py` with focused examples for current contracts (mode gating, symlink handling, phase doc section checks, duplicate-doc detection).
- Lock in exact finding codes/severity and key path semantics.

2. Extract rule groups behind existing API (`required_effort: medium`)
- Split `check_migration_consistency()` internals into small pure helpers by concern.
- Keep `check_migration_consistency()`, `has_blocking_consistency_findings()`, and `iter_visible_migration_dirs()` signatures unchanged.

3. Normalize shared internals (`required_effort: medium`)
- Consolidate repeated mode/status predicates into one explicit policy helper per contract family.
- Remove dead branches and tighten naming around “ready-publish metadata” vs “plan required”.

4. Integration verification sweep (`required_effort: low`)
- Validate behavior from migration CLI/doctor and planning publish call paths via existing tests plus small targeted additions.

## Risk profile
- Delivery risk: Low
- Regression risk: Low
- Interface risk: Low (no intended user-visible contract changes)
- Main failure mode: accidental finding ordering/message drift in tests that assert exact tuples.

## Best fit when
You want safer cleanup now and can defer larger policy changes.
