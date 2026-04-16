# Approach: exception-boundary-hardening

## Strategy
Focus the migration on module-boundary fault contract in `src/continuous_refactoring/artifacts.py` and keep behavior stable.

- Keep `ContinuousRefactorError` as the domain error surface, but add exception chaining (`from`) everywhere a low-level exception is translated.
- In `artifacts`, centralize error formatting for JSON/path I/O and raise domain errors only at boundaries that own persistence semantics.
- In `agent.run_observed_command` and `run_agent_interactive_until_settled`, preserve raw subprocess/threading signals by wrapping with causal chains and only changing message context at the boundary.
- In `config` and `git`, keep root causes from `JSONDecodeError`, `FileNotFoundError`, `OSError`, and `subprocess` failures instead of discarding them.
- In `loop` and `cli`, only add context once when switching from orchestration layer to user/runner layer.

## Tradeoffs
- Pros
  - Low blast-radius, high signal-to-noise improvement in diagnostics.
  - Directly matches the taste rule: translate at module boundaries, preserve root causes.
  - Minimal API changes and low refactor churn.
- Cons
  - Does not resolve existing structural coupling between `artifacts`, command execution, and targeting.
  - Message text changes may make a few brittle tests brittle if exact string assertions exist.

## Estimated phases
1. **Phase 1 — error inventory and baseline**
   - Capture current exception assertions from tests and a quick grep of `ContinuousRefactorError(...)` call-sites in `artifacts`, `agent`, `config`, `git`, `loop`, `cli`, `targeting`.
   - Add migration notes with expected unchanged status outputs (`completed`, `failed`, `interrupted`, etc.).
2. **Phase 2 — boundary hardening in modules**
   - Patch only non-control-flow behavior in:
     - `src/continuous_refactoring/artifacts.py`
     - `src/continuous_refactoring/agent.py`
     - `src/continuous_refactoring/config.py`
     - `src/continuous_refactoring/git.py`
   - Add `from exc` chains for all meaningful caught exceptions.
3. **Phase 3 — orchestration boundary alignment**
   - Update `src/continuous_refactoring/loop.py` and `src/continuous_refactoring/cli.py` to avoid duplicate translation and rely on boundary errors.
   - Ensure no new temporary marker names are introduced; use explicit outcome names only when representing real migration states.
4. **Phase 4 — lock behavior**
   - Update tests to assert causal chain presence (`__cause__`) on a small set of failure paths rather than only string equality.
   - Add one property-style test for `RunArtifacts.write_summary`/`iso_timestamp` ordering tolerance if relevant.

## Risk profile
- Risk level: **low to medium**.
- Operational risk: mostly log- and triage-facing; run logic unchanged.
- Regression risk: low if tests that assert exact text are adjusted as needed.
