# Approach: Backend Boundary Split

## Strategy
- Split backend-specific command behavior out of `src/continuous_refactoring/agent.py`.
- Create focused modules:
  - `src/continuous_refactoring/agent_backends.py` for supported-agent validation and command construction,
  - `src/continuous_refactoring/agent_claude_stream.py` for Claude stream-json extraction,
  - keep `agent.py` as the orchestration layer for interactive execution, settle handling, and observed command capture.
- Keep public imports stable through `agent.py`; no package-root re-export churn unless needed.

## Tradeoffs
- Strongest readability gain around the real domain seam: Codex and Claude are different products with different protocol handling.
- Makes future backend additions or behavior changes less likely to bloat the process-control code.
- Medium migration churn because tests and imports will move across files.
- Risk of over-splitting if backend logic remains tiny after cleanup.

## Estimated phases
1. Extract backend validation and command builders into `agent_backends.py` with no behavior changes.
   - `required_effort`: `medium`
2. Extract Claude NDJSON parsing into `agent_claude_stream.py` and retarget stream-json tests there.
   - `required_effort`: `low`
3. Reduce `agent.py` to orchestration glue plus interactive/process-control concerns.
   - `required_effort`: `medium`
4. Delete dead wrappers and duplicate private helpers once all callsites are stable.
   - `required_effort`: `low`
5. Run full pytest, paying extra attention to package export uniqueness and callsite imports.
   - `required_effort`: `low`

## Risk profile
- Technical risk: medium
- Blast radius: medium
- Failure modes:
  - Import cycles if orchestration and backend helpers are split in the wrong direction.
  - Private helper extraction accidentally weakening boundary errors or hiding unsupported-agent checks.
  - Test churn masking a subtle command-line regression.

## Best when
- The main pain is that backend concerns and process-control concerns are mixed together.
- We want a real module boundary without touching the heavier settle/watchdog code yet.
