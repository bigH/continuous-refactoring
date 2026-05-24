# Approach: Split Prompts by Domain Modules

## Strategy
Split `src/continuous_refactoring/prompts.py` into domain-focused modules (for example: `prompts_refactor.py`, `prompts_planning.py`, `prompts_phase.py`, `prompts_taste.py`) and keep a thin package-level `prompts.py` facade that preserves the current import surface.

## What Changes
- Move prompt constants/composers into domain modules with explicit `__all__`.
- Keep `continuous_refactoring.prompts` as compatibility boundary for current imports.
- Remove dead helpers discovered during split.
- Expand tests to cover both package-level exports and representative domain-level behaviors.

## Tradeoffs
- Pros: Stronger module boundaries; easier ownership and focused edits; lower per-file cognitive load.
- Cons: Highest churn; touches many imports/tests; increases coordination risk with package export uniqueness and boundary rules.

## Estimated Phases
1. Boundary design + export contract plan  
   - Scope: define module split and exact preserved public API from `continuous_refactoring.prompts`.  
   - required_effort: `high`
2. Mechanical extraction with compatibility facade  
   - Scope: move code into domain modules and re-export through existing boundary.  
   - required_effort: `xhigh`
3. Caller/test update pass  
   - Scope: update internals only where beneficial; keep external import behavior stable.  
   - required_effort: `high`
4. Cleanup + dead path deletion  
   - Scope: remove obsolete helpers and duplication revealed by split.  
   - required_effort: `medium`
5. Full verification + interface review checkpoint  
   - Scope: run full suite; explicitly call out any import/behavior change requiring human decision.  
   - required_effort: `medium`

## Risk Profile
- Overall risk: High.
- Primary risks: accidental API/export drift, import cycle regressions, broad test fallout.
- Mitigations: strict facade compatibility, staged extraction, explicit export tests, package import uniqueness checks.
- Human-review triggers: any change to public import paths, prompt text contracts, or CLI-facing behavior.
