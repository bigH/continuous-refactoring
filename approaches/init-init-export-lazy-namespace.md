# Approach: Lazy-Load Package Namespace via `__getattr__`

## Strategy
- Replace eager import-and-reexport side-effects in `src/continuous_refactoring/__init__.py` with explicit `__all__` and lazy symbol resolution via `__getattr__`.
- Keep exported API stable but defer module imports until first symbol access.
- Use cause-preserving wrapping only in namespace boundary failures (e.g., loader exception -> wrapped as `ContinuousRefactorError` with original exception attached) and avoid translation elsewhere.
- Keep `__SUBMODULES` for package contract visibility, but shrink initial work needed for import-time module graph.

## Tradeoffs
- Pros: faster and cleaner import path for package consumers, easier to spot import fan-in issues when one symbol fails to resolve.
- Cons: behavior shifts for side effects that depended on module import side-effects during package import; requires careful docs/tests for `hasattr`/`dir` expectations.
- Why this is taste-aligned: keeps compatibility paths safer (no hard cuts), uses explicit boundary mapping, uses truthful transitional naming (`migrating`/`stabilized` states where needed in plan docs).

## Estimated phases
1. Design a symbol-to-module map (static, not dynamic inference) and explicit `__all__` in `__init__`.
2. Implement `__getattr__` loader path and `__dir__` to keep introspection stable.
3. Add targeted tests in `tests/test_continuous_refactoring.py` and a small namespace-focused regression test verifying `hasattr` works for public exports.
4. Add a migration-readiness test run against `loop.py`/`prompts.py` entry usage to ensure the refactoring pipeline still imports cleanly.
5. Decide and lock rollback if lazy behavior introduces import timing regressions.

### Phased scope
- Files touched: `src/continuous_refactoring/__init__.py`
- Test touched: `tests/test_continuous_refactoring.py`

## Risk profile
- Technical risk: Medium to High
- Blast radius: Medium
- Failure modes:
  - subtle breakage in code that relies on eager module import side effects.
  - harder-to-diagnose delayed import failures during runtime.
- Mitigation: phase-gated activation with a hard stop plan after contract test failures; fallback to Approach 1 style if timing regression appears.
