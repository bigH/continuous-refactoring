# Approach: Artifacts contract + event schema migration

## Strategy
- Treat artifact persistence as a first-class boundary contract shared by `loop.py`, `agent.py`, and CLI entrypoints.
- Add a compact, strongly-shaped event schema while keeping command outputs and status strings unchanged.
- Replace open-ended mutable dict mutation with narrow mutators that enforce allowed keys and transitions.
- Convert module boundaries so exceptions are wrapped only where required:
  - I/O/parsing errors from artifact serialization at `artifacts` boundary.
  - callers consume `ContinuousRefactorError` and continue current branching.

## Why this fits this migration
- The co-change cluster has enough pressure to justify schema hardening:
  - migration routing, planning handoff, and loop retry logic all record progress in artifacts.
  - current structure is correct but implicit (no explicit event contract), so regression visibility is weak.

## Estimated phases
1. `src/continuous_refactoring/artifacts.py`: define event/count schema
   - Add small internal enums/constants:
     - attempt status keys
     - event field names
     - terminal status names (`completed`, `failed`, `interrupted`, etc.).
   - Introduce pure helpers:
     - `as_summary_payload() -> dict[str, object]`
     - `as_events_payload() -> list[dict[str, object]]` only if needed by callers.
   - Validate and clamp counts to known keys; unknown key writes in tests/logic become explicit failures.

2. `src/continuous_refactoring/loop.py`: explicit outcome logging only
   - Create tiny helper `log_attempt_event(artifacts, target_index, retry, event, **fields)` and replace scattered `artifacts.log(...)` calls that currently duplicate event naming.
   - Keep existing branch/commit/push semantics; no change to loop control branches.
   - Ensure `run_loop` and `run_once` finish in one place with the same final status fields.

3. `src/continuous_refactoring/agent.py` / `src/continuous_refactoring/cli.py`
   - Route command-run summaries through the event helper where useful (`run_once`/`run_loop` entrypoint messaging and interruption cases).
   - Keep CLI exit-codes unchanged.

4. `src/continuous_refactoring/git.py` + `src/continuous_refactoring/targeting.py`
   - Add schema-safe naming for any artifact-related fields carried through retries or random fallback attempts.
   - No behavioral changes; only name/shape hardening.

## Tradeoffs
- Pros
  - Better debugging and future compatibility for migration reports.
  - Enables stronger property-style tests on serialized artifact payloads and count invariants.
  - Keeps command semantics stable while making failures easier to localize.
- Cons
  - Higher immediate code churn than Approach 1.
  - Requires careful migration of all count updates to avoid silent omissions.
  - Slightly harder to read if too many tiny constants are introduced in one pass.

## Risk profile
- Risk: **Medium**
- Primary failure modes
  - strict schema rejects older on-disk payload assumptions in local workflows.
  - missed update path produces inconsistent attempt counters with existing tests and scripts.
- Control plan
  - run with backward-tolerant read path only (if feasible) and write strict schema on next writes.
  - keep event names stable (truthful names only; no `new/tmp/legacy` labels).

## Outcome expectation
- Recommended when you want stronger data guarantees now, not just mechanical cleanup.
