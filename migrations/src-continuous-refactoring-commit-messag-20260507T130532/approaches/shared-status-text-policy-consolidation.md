# Shared Status Text Policy Consolidation

## Strategy
Consolidate text-sanitization and fallback policy between `commit_messages.py` and `decisions.py` to remove split ownership of status-summary semantics. Introduce a single domain-focused policy entry point (likely in `decisions.py`) and convert `commit_messages.py` into a narrow orchestration layer.

## Tradeoffs
- Pros: Removes semantic drift risk between status summary and commit rationale behavior.
- Pros: Strong long-term maintainability if more status consumers appear.
- Cons: Higher blast radius across modules listed in the selected cluster.
- Cons: Requires careful human review because behavior influences commit text users see.

## Estimated Phases
1. **Cross-callsite inventory** (`required_effort: medium`)
   - Map all consumers of status/fallback sanitization and commit rationale expectations.
2. **Design unified policy boundary** (`required_effort: high`)
   - Define one canonical flow for sanitize -> normalize -> placeholder handling -> fallback.
3. **Implement consolidation** (`required_effort: high`)
   - Move/adapt logic with explicit boundary functions; preserve existing public signatures where possible.
4. **Behavior verification** (`required_effort: high`)
   - Expand tests in `tests/test_commit_messages.py` and adjacent decision-related tests; run full pytest.

## Risk Profile
- Implementation risk: Medium to High.
- Interface risk: Medium (user-visible commit-body text can subtly change).
- Regression risk: Medium to High due to distributed callsites.
- Rollback cost: Medium.
