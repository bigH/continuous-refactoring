# Approach: error-boundary-contract

## Strategy
Normalize exception ownership across `cli.py`, `loop.py`, `agent.py`, `config.py`, and `artifacts.py` so that domain meaning changes only at module boundaries and all boundary wraps preserve root causes with `from` chaining.

Keep user-facing behavior stable, keep call paths, and keep `run_once`/`run_loop` flow identical. The refactor focuses on translating failures from:
- command/process execution in `agent.py`
- manifest/config parsing and persistence in `config.py`
- migration routing orchestration in `loop.py`
- CLI orchestration and exit behavior in `cli.py`

and ensuring each boundary emits one consistent, causal error object.

## Why this approach fits the migration
This cluster is already error-heavy in runtime paths and has a lot of cross-module signal passing. Tightening boundary contracts reduces debug entropy without changing semantics, and directly matches taste directives about error translation only at boundaries and preserving signal.

## Tradeoffs
1. Pros: low churn, lower diagnosis cost, clearer error surfaces for humans and tests, minimal behavior risk if wrapped messages stay additive.
2. Cons: moderate test update burden where assertions currently check exact messages from wrapped exceptions.
3. Cons: one migration-wide naming pass is needed for new boundary-localized failure terms (`run_agent_failed`/`baseline_failed` etc.), which can briefly surface as churn in failure snapshots.

## Estimated phases
1. Boundary inventory: map current raises in target modules, and record exact call chain expectations from existing tests.
2. `agent.py` hardening: wrap process launch/output command failures with contextual `ContinuousRefactorError` and `from` chaining at command and interactive boundaries.
3. `config.py` hardening: keep payload decode, schema validation, and manifest write failures as boundary-owned, causal `ContinuousRefactorError`.
4. `loop.py` cleanup: remove redundant inline remaps, preserve original cause in migration and run-loop failures, and keep final-status transitions unchanged.
5. `cli.py` cleanup: centralize CLI exit translation at top-level dispatch only, keep inner modules pure with domain errors.
6. Validation lock: add/adjust targeted tests and lock exact boundary contracts where they are currently asserted.

## Validation
1. `uv run pytest tests/test_continuous_refactoring.py tests/test_config.py tests/test_loop_migration_tick.py tests/test_scope_loop_integration.py`
2. `uv run pytest tests/test_run.py tests/test_run_once.py tests/test_run_once_regression.py`
3. `uv run pytest tests/test_cli_init_taste.py tests/test_cli_review.py tests/test_cli_taste_warning.py`
4. Add property-based tests (or narrowed example-based if runtime cost is too high) for pure boundary helpers such as `_effective_max_attempts` and JSON manifest parsing invariants.

## Risk profile
- Risk level: medium-low.
- Primary technical risk is brittle error-message snapshots and parser-path tests.
- Operational risk is low because behavior contract remains, and only signal payloads (message text + stack shape) are intentionally narrowed.
