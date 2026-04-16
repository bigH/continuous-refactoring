# Approach: Artifacts boundary cleanup (surgical)

## Strategy
- Keep all public behavior stable and avoid touching orchestration semantics.
- Move `artifacts.py` from ad-hoc mutable bookkeeping to explicit, testable boundaries:
  - add explicit constants for attempt and count fields.
  - keep `RunArtifacts` methods small and deterministic.
  - make summary/event writes through shared private helpers with a single timestamp source.
- Tighten neighboring callsites only where behavior depends on artifact shape.
- Keep migration boundaries module-focused (no canary rollout), but keep compatibility in place.

## Why this fits this migration
- Direct evidence shows clustering around `artifacts.py` plus `loop.py`/`agent.py` consumers and CLI error paths.
- This is the highest signal-to-risk path: the touched surface is mostly persistence and callsite discipline, not refactoring logic.
- It directly addresses taste constraints:
  - exception wrapping stays in module boundaries (`artifacts`-facing writes should fail loudly with `ContinuousRefactorError`).
  - no speculative abstractions, minimal new docs/comments.
  - no feature-flag rollout.

## Estimated phases
1. `src/continuous_refactoring/artifacts.py`: contract extraction
   - Add internal field registries for:
     - canonical counter keys
     - attempt log keys
     - summary payload shape (private helper returning a serializable dict).
   - Add a private atomic `write_json(path, payload)` helper and route all JSON writes through it.
   - Keep public methods (`attempt_dir`, `baseline_dir`, `mark_attempt_started`, etc.) API-compatible.
   - Preserve dataclass types; only tighten validation on index inputs and deterministic sorting.

2. `src/continuous_refactoring/loop.py`: low-friction callsite alignment
   - Replace any direct assumptions of summary payload internals with a local helper like
     `artifacts.current_summary()` if introduced, otherwise keep callers unchanged.
   - Normalize status strings used in `artifacts.finish(...)` to existing values.
   - Add one helper around migration/loop branch commit flow that writes status+artifact updates once.

3. `src/continuous_refactoring/cli.py` + `src/continuous_refactoring/config.py`
   - Remove duplication by using config-level helpers for paths where they already exist semantically (taste/global dir paths remain here unless migration dictates).
   - Keep CLI-level behavior and exit paths unchanged.

4. `src/continuous_refactoring/git.py` + `src/continuous_refactoring/targeting.py`
   - Apply one pass of cleanup only where artifacts state is passed through (pure ref names only; no logic changes).

## Tradeoffs
- Pros
  - Lowest behavioral risk: stable method signatures and minimal control-flow changes.
  - Easier to validate: mostly deterministic file I/O and schema checks.
  - Good base for later, deeper migrations.
- Cons
  - Leaves duplicated orchestration intent in `loop.py`; no big architectural simplification.
  - Does not reduce complexity from broad retry/branch paths in this pass.
  - More follow-up migrations needed for deeper testability gains.

## Risk profile
- Risk: **Low**
- Primary failure modes
  - summary payload shape regressed by serialization changes.
  - race-like ordering of artifact writes if helper calls are not mirrored in all mutation paths.
- Control plan
  - keep `create_run_artifacts`, `attempt_dir`, `write_summary`, and `log` semantics behavior-compatible.
  - add explicit per-phase checks around changed payload shape and existing run artifact files.

## Outcome expectation
- Recommended when you want safe migration progress quickly and want broad confidence before any control-flow rewiring.
