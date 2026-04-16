# Approach: package-boundary-slimming

## Strategy
Treat migration as a boundary-cleanup pass for package entrypoints, keeping runtime behavior stable but reducing accidental coupling around `artifacts` imports.

- Replace dynamic aggregation in `src/continuous_refactoring/__init__.py` with explicit exports.
- Use direct imports at call sites (`from continuous_refactoring import artifacts` style only where needed) and stop re-exporting half the package surface during import-time bootstrap.
- Keep migration scope anchored on `artifacts` by introducing a canonical package API docstring and explicit FQNs:
  - `artifacts.RunArtifacts`, `artifacts.RunArtifactsAttempt`-style naming kept meaningful.
- In `cli.py` and `loop.py`, avoid importing unnecessary modules via package-level indirection.
- In `agent.py` and `config.py`, avoid broad dependency on package import side effects.

## Tradeoffs
- Pros
  - Cleaner import graph and clearer module boundaries.
  - Faster import diagnostics and easier failure isolation.
  - Matches taste preference for meaningful module boundaries and less mechanical reshaping.
- Cons
  - Not purely about migration semantics; can be controversial if callers rely on existing package re-exports.
  - Possible temporary breakage for external importers until compatibility path is accounted.

## Estimated phases
1. **Phase 1 — compatibility assessment**
   - Inventory external/internal consumers of package-level re-exports.
   - Keep a compatibility shim only if callers outside this repo are known.
2. **Phase 2 — explicit exports**
   - Rewrite `__init__.py` to static, explicit exports and remove looped module import behavior.
   - Ensure `ContinuousRefactorError` and `RunArtifacts` remain reachable for existing in-repo callers.
3. **Phase 3 — call-site cleanup**
   - Update imports in `agent.py`, `cli.py`, `loop.py`, `config.py`, and `targeting.py` only where ambiguity exists.
4. **Phase 4 — behavioral lock**
   - Add import-level smoke checks to prevent breakage.
   - Keep migration state names and rollout constants explicit and truthful.

## Risk profile
- Risk level: **medium**.
- Operational risk: medium (public import surface risk), low runtime execution risk.
- Validation focus: import and startup paths.
