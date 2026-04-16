# Run orchestration as a typed pipeline

## Strategy
- Refactor `run_once` and `run_loop` around a shared run pipeline object (`RunAttemptContext`) so retry rules, branch handling, and commit/push side effects are explicit and consistent.
- Standardize outcome names with truthful transition states (`versionBeingRolledOut` style naming used only if temporary rollout metadata is needed) and reuse one set of constants across planning, fix-up, and migration-routing paths.
- Keep behavior unchanged from the user perspective; the direct execution path remains unchanged while reducing ad-hoc branching.

## Tradeoffs
- Pros
  - Major reduction in duplicated retry + branching logic.
  - Cleaner migration-ready flow from route decision to final artifact updates.
  - Easier to validate each phase independently (agent result, test result, commit/push).
- Cons
  - Touches the busiest orchestration functions; high blast radius for control flow changes.
  - Hardest to get exactly right without widening temporary abstraction if not tightly scoped.

## Estimated phases
1. **Define domain types and outcomes**
   - Add small enums/dataclasses in `loop.py` for route outcomes, attempt outcomes, and final status.
   - Keep existing public behavior values for logs (artifact counts, commit messages) to preserve compatibility.
2. **Unify `run_once` and `run_loop` retry engine**
   - Factor out a shared `execute_attempt()` helper that encapsulates:
     - target model/effort resolution
     - test baseline guard
     - optional `max_attempts` handling
     - rollback semantics
     - commit/push decision.
3. **Align phase path with routing path**
   - Ensure migration routing (`_route_and_run`) and non-routing path share status transitions and failure reasons.
   - Keep `run_once` as a thin wrapper over the same helpers to avoid two mental models of same behavior.
4. **Safety cleanup**
   - Remove repetitive status strings from flow control where replaced by enum members.

## Risk profile
- Risk level: **High** if done in one step.
- Failure modes: accidental early-return/continue changes, regression in `--max-attempts` edge cases, and subtle baseline behavior changes when `targets` are empty.
- Mitigation: keep helper API tiny, make changes in two passes (first helper extraction, second wiring), and preserve exact `--max-attempts` math as-is.

## Migration footprint
- `src/continuous_refactoring/loop.py`
- `src/continuous_refactoring/cli.py` (status/result messaging only if needed)
- `src/continuous_refactoring/artifacts.py` (if counters need richer status buckets)
