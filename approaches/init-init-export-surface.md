# Approach: Surface-Clarity Refactor for `__init__.py`

## Strategy
- Keep current re-export model and behavior intact, but make it explicit and inspectable.
- In `src/continuous_refactoring/__init__.py`, replace the raw tuple of imports with a small set of explicit module entries plus one `collect_package_exports()` helper.
- Enforce duplicate detection with origin-aware error messages (module + symbol), preserving full cause chains on lower-level errors only where raised.
- Keep `__SUBMODULES` and exported symbols backward-compatible for existing tests and callers.
- No module split or new runtime behavior outside package init.

## Tradeoffs
- Pros: very low blast radius, low behavioral risk, minimal API churn, direct migration to stable `__all__` contract.
- Cons: still keeps `__init__.py` as the central export hub and does not change the eager-import profile.
- Why this is taste-aligned: it avoids speculative boundaries, keeps module boundaries stable, and improves clarity without touching dead/legacy code paths.

## Estimated phases
1. Capture current export expectations in tests
   - Add/extend assertions for stable symbol presence and deterministic export order if useful.
2. Introduce a structured `_PUBLIC_MODULES` list and extraction helper in `src/continuous_refactoring/__init__.py`
   - Preserve module import order and public-only behavior.
3. Upgrade duplicate-symbol checks to include duplicate provenance details while keeping same failure contract.
4. Add a tiny regression test for internal-module re-export exclusion still holding (`migration_manifest_codec` remains module-private to package root).
5. Run focused package contract tests.

### Phased scope
- File touched: `src/continuous_refactoring/__init__.py`
- Test touched: `tests/test_continuous_refactoring.py`

## Risk profile
- Technical risk: Low
- Blast radius: Low
- Failure modes:
  - Hidden breakage if symbol collection accidentally drops a symbol due descriptor typo.
  - Slightly harder-to-spot import-time failures if one of the modules in the explicit list raises on import.
- Mitigation: phase gates with existing package contract tests before migration write path changes.
