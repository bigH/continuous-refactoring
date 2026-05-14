# Approach: Interface-First Boundary Hardening

## Strategy
Start by hardening behavior at module boundaries (`migrations.py`, `migration_tick.py`) where errors and eligibility decisions cross system interfaces. Lock externally visible behavior with tests first, then refactor internals behind those tests.

## Why this approach
- Best fit for shipped-system safety rules: boundary behavior is explicit before cleanup.
- Aligns with taste: wrap/translate errors only at module boundaries, not deep internals.
- Minimizes accidental CLI/XDG/migration-contract drift.

## Tradeoffs
- Slower upfront because contract tests come first.
- Some duplication may remain temporarily while preserving behavior.
- Less dramatic early code simplification than an aggressive cut.

## Estimated Phases

### Phase 1: Lock boundary/error contracts
- Scope: `src/continuous_refactoring/migrations.py`, `src/continuous_refactoring/migration_tick.py`, focused tests.
- Work: add/adjust tests for load/save manifest boundary errors, manifest eligibility, and consistency/preflight failures.
- required_effort: `low`
- Risk: Low.

### Phase 2: Refactor boundary helpers and call flow
- Scope: same modules, no CLI surface changes.
- Work: tighten helper decomposition for manifest candidate enumeration and preflight consistency flow; remove redundant branches while preserving outcomes.
- required_effort: `medium`
- Risk: Medium (behavioral equivalence risk in routing/tick sequencing).

### Phase 3: Cross-check planning prompt/test consistency
- Scope: `tests/test_prompts.py`, `tests/test_planning_publish.py` only as needed for invariants touched by refactor.
- Work: ensure prompt/test contracts still reflect migration semantics after cleanup.
- required_effort: `low`
- Risk: Low.

## Risk Profile
- Overall risk: Low to Medium.
- Primary failure mode: subtle ordering change in migration candidate selection.
- Mitigation: contract tests first; run targeted tests before full suite.

## Rollback posture
- Safe rollback by reverting Phase 2 only, because Phase 1 contract tests define baseline behavior.
