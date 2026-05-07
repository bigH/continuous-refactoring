# Policy Extraction and Pure Rules

## Strategy
Refactor `commit_messages.py` around explicit, pure helper rules: one helper for value normalization/presence, one for rationale candidate ordering, one for commit message section assembly. Keep sanitization delegated to `decisions.py`, but make policy ordering and placeholder filtering first-class and test-driven.

## Tradeoffs
- Pros: Improves readability and local reasoning; easier to extend rationale policy later.
- Pros: Better test granularity on pure helpers.
- Cons: Slightly larger internal surface area (more helpers).
- Cons: If helpers leak into exports, import surface must be guarded carefully.

## Estimated Phases
1. **Test matrix expansion** (`required_effort: medium`)
   - Add behavior tables for candidate precedence and placeholder suppression.
2. **Internal helper extraction** (`required_effort: medium`)
   - Introduce private pure helpers; keep public API unchanged.
3. **Optional cross-module consistency pass** (`required_effort: high`)
   - Audit `decisions.status_summary` and neighboring callsites for ordering consistency language only (no contract change).
4. **Validation and review** (`required_effort: low`)
   - Run focused + full pytest.

## Risk Profile
- Implementation risk: Medium.
- Interface risk: Low if exports remain unchanged; Medium if helper visibility drifts.
- Regression risk: Medium (policy reorder mistakes possible).
- Rollback cost: Low to Medium.
