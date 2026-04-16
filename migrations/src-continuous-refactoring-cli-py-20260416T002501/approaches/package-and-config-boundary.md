# Approach: Package and config boundary clarity without flow churn

## Strategy
- Keep CLI and loop behavior intact, but tighten module boundaries for fewer hidden couplings:
  - `__init__.py`: replace broad dynamic re-export loop with explicit, deterministic symbol export assembly.
  - `config.py`: isolate manifest/taste helper functions used by CLI into named boundary helpers (`project_or_raise`, `taste_path_for_current_project`, etc.).
  - `cli.py`: remove local inline config glue and delegate to config boundary helpers.
- This approach is a clean-up with low churn and aligns with taste guidance on meaningful domain boundaries and minimal wrapper layers.
- Keep rollout naming truthful where transitional behavior exists and avoid temporary naming patterns.

## Why this migration is viable
- Cluster already has recent co-changes around taste/config and CLI handlers; making these boundaries explicit avoids import-time surprises.
- Existing behavior can stay stable while removing accidental opacity in startup paths.

## Tradeoffs
- Pros
  - Low implementation risk and low blast radius.
  - Faster review: mostly mechanical import and helper moves.
  - Easier future testing since config resolution and CLI argument orchestration are separate.
- Cons
  - Does not reduce deeper orchestration duplication in loop.
  - Limited functional payoff by itself; mostly debt reduction.

## Estimated phases
1. **Export boundary hardening**
   - Make `src/continuous_refactoring/__init__.py` explicit and stable.
   - Keep existing public symbol names; only change composition mechanics.
2. **Config boundary extraction**
   - Move repeated taste and project checks from `cli.py` into `config.py` helpers.
   - Keep error messages authored in CLI for user-facing consistency.
3. **CLI handler simplification**
   - Replace inlined helper calls with thin calls into config/config-aware helpers.
   - Keep command handlers in `cli.py` as a pure dispatch layer.
4. **Prompt-facing cleanup (optional)**
   - If touched during validation, remove low-value comments/docstrings in `prompts.py` helpers that describe obvious behavior.

## Risk profile
- Risk level: Medium-Low.
- Main risk: import-order change if consumers relied on dynamic `__all__` behavior.
- Control plan: keep exact symbol names and avoid changing public symbols; only change how aggregation is assembled.

## Migration footprint
- `src/continuous_refactoring/__init__.py`
- `src/continuous_refactoring/config.py`
- `src/continuous_refactoring/cli.py`
