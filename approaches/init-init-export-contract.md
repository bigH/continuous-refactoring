# Approach: Contract-Driven Public Surface Descriptor

## Strategy
- Move exported-public definition out of runtime module-order magic into `src/continuous_refactoring/public_api.py`.
- Define a compact, explicit `PUBLIC_REEXPORTS` descriptor (module_name, symbol, optional alias) and drive `__init__.py` from that list.
- Keep package runtime behavior: same names still appear in `continuous_refactoring.__all__`, same re-exported callsites, same hidden-module boundary.
- Keep `__SUBMODULES` for import validation, but source of truth for API moves to descriptor data.

## Tradeoffs
- Pros: clearer intent, easier code review for future API changes, simpler to detect stale/manual exports, aligns with domain-focused boundaries and naming truthfulness.
- Cons: adds one new module and one migration step to validate descriptor integrity.
- Why this is taste-aligned: no speculative abstractions, clear readability gain, explicit compatibility over convenience.

## Estimated phases
1. Add `src/continuous_refactoring/public_api.py` with a typed re-export descriptor + minimal validation helpers.
2. Refactor `src/continuous_refactoring/__init__.py` to build `__all__` from descriptor + runtime imports only.
3. Add descriptor-level tests in `tests/test_continuous_refactoring.py` for:
   - all exported names present,
   - no duplicate symbol names in descriptor,
   - internal module not re-exported (`migration_manifest_codec` remains private).
4. Add a migration check that compares generated `__all__` to a non-empty known set to prevent accidental empty exposure.
5. Run targeted contract tests for package init and prompt/loop import flows.

### Phased scope
- Files touched: `src/continuous_refactoring/__init__.py`, `src/continuous_refactoring/public_api.py`
- Test touched: `tests/test_continuous_refactoring.py`

## Risk profile
- Technical risk: Medium
- Blast radius: Medium
- Failure modes:
  - New descriptor errors can hide symbols if import paths drift.
  - More churn touching two new files means merge conflict potential during rapid migrations.
- Mitigation: keep descriptor small and strictly validated before touching any loop/routing logic.
