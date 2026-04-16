# Approach: package-boundary-slimming

## Strategy
Refactor `src/continuous_refactoring/__init__.py` from dynamic module-driven exports to explicit module re-exports and a typed, minimal public surface.

Keep each module owning its own API and keep `continuous_refactoring.__all__` as a curated, stable boundary contract. Remove dynamic import-driven discovery, which is harder to reason about and can hide import cycles.

## Why this approach fits the migration
This is a domain-boundary cleanup with low semantic blast radius: it does not alter runtime behavior, but makes module boundaries explicit and removes a hidden coupling between `__init__` and every imported module.

## Tradeoffs
1. Pros: clearer exports, easier reviewer signal on added/removed public API, better alignment with FQN-focused taste.
2. Pros: avoids import-time side effects from pulling modules eagerly via dynamic loops.
3. Cons: requires a small maintenance cost when new public functions are added in future modules.
4. Cons: touches import surface that many tests and downstream consumers may rely on; snapshot style tests must stay green.

## Estimated phases
1. Replace the module list iteration with explicit `from .module import ...` and explicit `__all__` composition.
2. Add a small lintable assertion in `__init__.py` to keep duplicate export names impossible.
3. Keep the package-level exports stable and sorted as a regression contract.
4. Run full package export surface tests and full targeted CLI/run suites as smoke.

## Validation
1. `uv run pytest tests/test_continuous_refactoring.py`
2. `uv run pytest tests/test_cli_init_taste.py tests/test_e2e.py`
3. `uv run pytest tests/test_config.py tests/test_loop_migration_tick.py tests/test_run.py` (unchanged import paths only)

## Risk profile
- Risk level: low.
- Primary technical risk is accidental public API drift; mitigated by test_lock on `continuous_refactoring.__all__` and import-style assertions.
- Operational risk is low since behavior is boundary-centric and observable only through exports.
