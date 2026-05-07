# Minimal Rationale Hardening

## Strategy
Keep `src/continuous_refactoring/commit_messages.py` as a thin formatter module and tighten only edge behavior around rationale selection and message normalization. Focus on deterministic, easy-to-read condition flow with no external contract changes.

## Tradeoffs
- Pros: Lowest blast radius; likely zero behavior drift outside target tests.
- Pros: Preserves current module boundaries (`decisions.py` still owns sanitization).
- Cons: Leaves some duplication/implicit policy (placeholder matching, empty normalization) in this module.
- Cons: Smaller readability win than deeper extraction.

## Estimated Phases
1. **Codify current behavior in tests** (`required_effort: low`)
   - Add/expand example-based tests for punctuation/casing variants, whitespace-only inputs, and subject/why trimming.
2. **Refactor local control flow only** (`required_effort: low`)
   - Flatten conditional branches in `commit_rationale`/`build_commit_message` without changing signatures.
3. **Regression validation** (`required_effort: low`)
   - Run focused tests (`tests/test_commit_messages.py`) and then full pytest.

## Risk Profile
- Implementation risk: Low.
- Interface risk: Low (no CLI/state/schema changes).
- Regression risk: Low, mostly around subtle placeholder matching.
- Rollback cost: Low.
