# Approach: exception-boundaries

## Strategy
Refactor only the command-runner boundary in `agent.py` with a strict error policy: preserve underlying causes inside helper layers and wrap only at module boundaries where domain signal changes.

The changes are intentionally constrained to `agent.py` and tests that cover it (`test_continuous_refactoring.py` and `test_run_once.py`/`test_run` where command exceptions are observed indirectly). Public call sites in `loop.py` and `phases.py` should remain unchanged except for relying on richer error messages.

## Why this fits
Most current refactoring signal is diluted by generic `ContinuousRefactorError("...")` messages that lose root causes (`FileNotFoundError`, `OSError`, `ValueError` from parsing, etc.). This approach improves debuggability with minimal shape change and avoids speculative module extraction.

## Tradeoffs
1. Pros
   - Low migration blast radius (single file + targeted tests).
   - Improves failure triage without changing success semantics.
   - Aligns with taste: "translate only at module boundaries" and "preserve causes when translating."
2. Cons
   - Some call sites will produce slightly longer exception strings.
   - No structural simplification beyond error handling, so deeper duplication remains.

## Estimated phases
1. Baseline
   - Run narrow targeted tests around current behavior: `uv run pytest tests/test_continuous_refactoring.py tests/test_loop_migration_tick.py::test_route_and_run_maybe` (or the matching minimal subset that exercises `maybe_run_agent` and retry handling).
2. Error-surface hardening in `agent.py`
   - Add exception chaining (`from error`) for all wrapped runtime failures.
   - Keep `ContinuousRefactorError` as-is; do not convert to custom hierarchy.
   - Replace broad `except` branches that intentionally swallow context with explicit narrow branches and `from` propagation where actionable.
3. Boundary consistency pass
   - Ensure all call sites that raise from `agent.py` include boundary-meaningful context only, not per-syscall detail.
4. Validation and stabilization
   - Add/adjust tests asserting cause chain is preserved for missing executable, timeout/stall, and terminal-control fallback paths.
   - Keep output contracts from existing tests intact.

## Risk profile
- Risk level: low.
- Operational risk: low; runtime behavior should not change except richer exception chain and message wording on failures.
- Validation risk: moderate-low, mainly around tests that assert exact strings.

