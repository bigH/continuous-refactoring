# Approach: artifact-core-model

## Strategy
Refactor `src/continuous_refactoring/artifacts.py` into a tighter domain model and consume it from the cluster as the single source of truth for run state.

- Keep exported API stable (`create_run_artifacts`, `RunArtifacts`, `AttemptStats`) but make state operations explicit and narrow:
  - explicit attempt state transitions (`started -> completed -> finalized`),
  - explicit count updates with named methods,
  - one-path summary/event serialization helper.
- Introduce an internal `RunArtifactsStore` in `artifacts.py` that owns JSONL/event/snapshot writes and path creation.
- In `loop.py`, route `run_once` and `run_loop` through these new methods instead of directly mutating dataclass fields.
- In `cli.py`, preserve command-line behavior while surfacing cleaner artifact lifecycle hooks.
- Add strict migration state vocabulary for any transitional fields/vars: `upgraded`, `versionBeingRolledOut`, `canary` only when semantically needed.

## Tradeoffs
- Pros
  - Cleaner domain model with stronger invariants around attempts and counts.
  - Easier future migration logic because run artifacts become explicit protocol, not ad-hoc dict writes.
  - Better alignment with taste preference for readability and flow-level abstractions.
- Cons
  - Medium behavior risk in hot loop path (commit/push counters, status strings, summary files).
  - More refactor coupling across `loop`, `artifacts`, and tests.
  - Wider code delta can increase review load.

## Estimated phases
1. **Phase 1 — model contract**
   - Define clear state transition methods in `artifacts.py` and document intended invariants.
   - Keep public symbols in place to avoid broad import churn.
2. **Phase 2 — migrate call sites**
   - Update `run_once` and `run_loop` to use the new artifact transition API for:
     - attempt lifecycle,
     - commit/push recording,
     - summary/event writes.
3. **Phase 3 — compatibility tests and fixture migration**
   - Add table-driven tests for `RunArtifacts` transitions and idempotent `write_summary`.
   - Adjust any integration tests expecting interim `counts` shape or event ordering.
4. **Phase 4 — verification sweep**
   - Run focused loop/migration tests and a targeted smoke path through `run_once`/`run_loop`.
   - Keep behavior unchanged for success/failure exit codes.

## Risk profile
- Risk level: **medium**.
- Operational risk: higher than Approach 1 because `loop.py` flow is mission critical.
- Control: strict phase boundaries and parity checks before moving forward.
