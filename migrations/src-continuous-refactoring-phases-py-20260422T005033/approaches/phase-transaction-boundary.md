# Phase Transaction Boundary

## Strategy

Keep readiness in `phases.py`, but extract the execution transaction into a small internal abstraction that makes rollback, retry, validation, and manifest completion explicit.

Possible shape:

- `PhaseExecutionRequest`
  - phase, manifest, taste, repo paths, agent settings, validation command, retry budget
- `PhaseAttemptResult`
  - agent status, phase reached, summary, focus, return code, validation status
- `PhaseTransaction`
  - captures `head_before`
  - runs one attempt
  - rolls back between retries
  - returns `ExecutePhaseOutcome`

This is not an interface. It is one concrete helper for a real multi-step transaction. The public function `execute_phase()` becomes a thin constructor/call wrapper.

## Tradeoffs

Pros:
- Names the transaction currently hidden inside `execute_phase()`.
- Makes retry behavior and rollback lifecycle easier to test in isolation.
- Reduces parameter plumbing once the request object exists.
- Gives future phase-execution changes a coherent home without splitting files immediately.

Cons:
- More abstraction than the in-place helper approach.
- A class can become a junk drawer if it owns too much state.
- Some tests may need to assert outcomes through `execute_phase()` anyway, limiting isolation value.
- Slightly higher risk of over-structuring a module that only has one concrete execution path.

## Estimated Phases

1. **Define the transaction contract in tests**
   - Add outcome tests for rollback before retries, terminal failure rollback, validation exception handling, and manifest completion cleanup.
   - Keep tests behavior-oriented; avoid asserting private method calls.

2. **Introduce request/result values**
   - Add frozen dataclasses for repeated execution inputs and per-attempt results.
   - Keep them private unless callsites outside `phases.py` genuinely need them.

3. **Move retry loop into the transaction**
   - Preserve artifact paths and call roles exactly.
   - Keep exception translation at the phase execution boundary.
   - Leave `execute_phase()` as the stable public entrypoint.

4. **Simplify completion**
   - Extract manifest phase completion into a small pure-ish helper.
   - Run `uv run pytest tests/test_phases.py` first, then `uv run pytest`.

## Risk Profile

Medium risk. The abstraction can clarify the lifecycle, but it also introduces more moving parts than a simple helper extraction.

Main watch-outs:
- Do not introduce a speculative protocol or interface; there is one implementation.
- Avoid a mutable stateful object with hidden transitions. Prefer explicit returned values.
- Keep `ContinuousRefactorError` translation at the boundary; do not wrap internal helper failures unless the caller gets better signal.
- Retry budget behavior must stay exact, including `max_attempts is None`.

## Best Fit

Choose this when the team expects more phase execution behavior soon: richer validation summaries, retry policy changes, or additional completion bookkeeping. If no such change is imminent, the in-place pipeline is cleaner.
