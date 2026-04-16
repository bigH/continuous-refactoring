# Approach: package-boundary-simplification

## Strategy
Use this migration as an import-shape hygiene pass around the git cluster, keeping behavior stable but making module intent and public surfaces less accidental.

- Replace `src/continuous_refactoring/__init__.py` dynamic export assembly with explicit exports.
- Keep legacy imports working for now by preserving current public names from this package; avoid compatibility hard cuts.
- Make `git.py` the authoritative import target for git helper ownership and reduce indirect imports through package-level re-exports.
- Use `run_command` and branch helpers directly in callers where currently implicit through `continuous_refactoring.git` aliasing is unclear.

## Tradeoffs
- Pros: clearer FQNs, less hidden import-time behavior, faster failure localization around `git.py` and package init.
- Cons: touches public-facing package boundary and requires compatibility caution for external callers.

## Estimated phases
1. **Phase 1 — Compatibility audit**
   - Inventory internal and repository tests that rely on package-level exports.
   - Confirm no migration contract depends on import-order side effects from `__init__.py`.

2. **Phase 2 — Explicit package API**
   - Refactor `src/continuous_refactoring/__init__.py` to explicit module and symbol exports.
   - Keep duplicates impossible and remove mechanical module iteration.

3. **Phase 3 — Direct call-site alignment**
   - Update affected imports in `loop.py` and `phases.py` only to reduce ambiguity and preserve behavior.
   - Do not introduce intermediate abstraction layers.

4. **Phase 4 — Stability gate**
   - Add import-shape tests for package namespace and key call paths.
   - Suggested command set:
     - `uv run pytest tests/test_continuous_refactoring.py tests/test_loop_migration_tick.py`
     - `uv run pytest tests/test_run.py tests/test_run_once.py`
     - `uv run pytest tests/test_prompts.py`

## Risk profile
- Risk: **medium-high** due to public API surface.
- Regression risk: potential for import failures in external users even with stable in-repo tests.
- Rollout risk: medium; if this is preferred, keep a conservative compatibility statement in `__init__` for a few releases before cleanup.
