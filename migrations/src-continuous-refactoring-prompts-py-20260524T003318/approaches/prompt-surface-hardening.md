# Approach: Prompt Surface Hardening

## Strategy
Keep `src/continuous_refactoring/prompts.py` as one module, but tighten its public contract and reduce regression risk by converting brittle literal checks into explicit, reusable output-contract anchors. Preserve all current CLI/runtime behavior and prompt semantics.

## What Changes
- Add/normalize named prompt contract anchors (small constants/functions) for repeated required clauses.
- Replace duplicated inline phrase assembly with small local helpers where repetition is currently high.
- Keep all exported names stable unless dead exports are proven unused by repo-wide evidence.
- Expand `tests/test_prompts.py` around invariants that currently rely on scattered literal string checks.

## Tradeoffs
- Pros: Lowest blast radius; fastest path to cleaner maintenance; strongest behavior preservation.
- Cons: Does not materially reduce module size or conceptual coupling; still string-template heavy.

## Estimated Phases
1. Baseline + contract inventory  
   - Scope: map required clauses used by tests/callers; identify repetition and dead branches.  
   - required_effort: `low`
2. Internal prompt-contract consolidation  
   - Scope: extract repeated clauses to local helpers/constants without changing final rendered text contracts.  
   - required_effort: `medium`
3. Test hardening for prompt invariants  
   - Scope: add/adjust tests to validate stable contract points and taste injection expectations.  
   - required_effort: `medium`
4. Final verification + review note  
   - Scope: run targeted prompt tests and full pytest; document any intentional text-shape change for human review if present.  
   - required_effort: `low`

## Risk Profile
- Overall risk: Low.
- Primary risks: accidental wording drift in prompts that breaks downstream parsing or brittle tests.
- Mitigations: keep contract strings centralized, preserve status-block delimiters verbatim, run full `uv run pytest` before completion.
- Human-review triggers: any intentional user-visible CLI prompt wording change beyond internal deduplication.
