# Approach: Composable Prompt Builders

## Strategy
Refactor `prompts.py` into clearer domain-focused builder sections (refactor/run prompts, planning prompts, migration review prompts, taste prompts), using typed intermediate builders that compose sections deterministically. Keep public function signatures and exported constants stable.

## What Changes
- Introduce explicit section-builder helpers per prompt family.
- Normalize shared context rendering (taste block, work-dir/live-dir constraints, retry context) through one composition path.
- Reduce ad-hoc string concatenation in top-level composition functions.
- Update tests to validate both contract text and cross-family consistency.

## Tradeoffs
- Pros: Better readability and change locality; easier future prompt edits with less accidental divergence.
- Cons: Moderate churn in a high-touch module; requires careful parity checks across many callers/tests.

## Estimated Phases
1. Prompt family map + invariants spec  
   - Scope: identify families, shared clauses, and must-not-change boundary behavior.  
   - required_effort: `medium`
2. Introduce composable builders behind existing APIs  
   - Scope: refactor internals while preserving `__all__` exports and call contracts.  
   - required_effort: `high`
3. Consistency unification  
   - Scope: route duplicated context sections through shared builder utilities; remove dead local formatting paths.  
   - required_effort: `medium`
4. Test adaptation + parity checks  
   - Scope: keep existing assertions green; add parity checks for critical prompts and status block structure.  
   - required_effort: `medium`
5. Full validation + migration notes  
   - Scope: run full suite and surface interface-impact statement for human review if wording changed.  
   - required_effort: `low`

## Risk Profile
- Overall risk: Medium.
- Primary risks: subtle text-order changes impacting tests or downstream parsing behavior.
- Mitigations: golden/parity assertions for high-risk prompts; incremental refactor by family; keep public exports unchanged.
- Human-review triggers: any changed clause that could alter operator expectations in planning/review flows.
