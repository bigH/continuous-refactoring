# Phase 2: Internal Effort Resolution Cleanup

required_effort: medium
effort_reason: Cross-module effort-resolution cleanup can silently drift CLI/migration behavior without careful contract-preserving verification.

## Scope
- `src/continuous_refactoring/effort.py`
- Minimal adjacent call sites if required for coherence (for example `loop.py`, `migration_tick.py`, or CLI argument plumbing)
- `src/continuous_refactoring/__main__.py` only if there is a concrete readability gain with zero behavior drift
- Tests that validate effort defaults/caps and run semantics

## Goals
- Reduce internal repetition and improve readability in effort resolution paths.
- Preserve all externally visible effort semantics exactly.

## Precondition
- Phase 1 is complete.
- Contract-guarding tests for boundary behavior are present and passing locally.
- Current effort interfaces (default `low`, cap `xhigh`, target override cap behavior, migration defer-on-over-cap behavior) still exist and are encoded in tests.

## Implementation Instructions
1. Introduce small pure helpers to centralize effort normalization/capping where duplication currently exists.
2. Keep behavior identical at boundaries: CLI defaults, cap enforcement, and phase deferral semantics must not change.
3. Keep abstraction depth shallow; prefer direct, readable flow over framework-like layering.
4. Only touch `__main__.py` if it materially reduces ambiguity without changing invocation behavior.

## Validation Steps
- Run focused effort/CLI/run tests:
  - `uv run pytest tests/test_effort.py`
  - `uv run pytest tests/test_cli.py tests/test_run.py tests/test_run_once.py`
  - `uv run pytest tests/test_loop_migration_tick.py`
- Run full validation command:
  - `uv run pytest`

## Definition of Done
- Internal effort-resolution logic is simpler (less duplication / clearer flow) with no interface drift.
- Existing boundary tests from Phase 1 remain green without contract assertion changes that weaken coverage.
- Full configured validation command passes.
- Repository remains shippable with unchanged user-visible effort behavior.
