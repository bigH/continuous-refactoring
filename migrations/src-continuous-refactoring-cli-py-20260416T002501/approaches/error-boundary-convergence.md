# Approach: CLI-to-loop error boundary convergence

## Strategy
- Keep command behavior stable, but normalize failure handling in one place:
  - `loop.py` raises only domain errors (`ContinuousRefactorError`/`RuntimeError` subclasses) and never calls `SystemExit`.
  - `cli.py` remains the process boundary: parse + print concise user-facing errors + exit code mapping.
- Move all command-gating failures currently hidden inside handlers (`_resolve_taste_path`, `_validate_targeting`, `_handle_review_*`, run entrypoints) into a shared boundary contract.
- Keep all modules domain-focused:
  - `loop.py`: orchestration and outcome semantics.
  - `config.py`: project/taste/load/version checks.
  - `cli.py`: argument surface + boundary translation.
- Enforce exception nesting where crossing module boundaries so signal is preserved but caller context is clear.

## Why this migration is viable
- The cluster currently has mixed return paths:
  - `loop.py` and `cli.py` both throw `SystemExit` in places, which makes failure intent noisy and hard to reason about at module boundaries.
  - Several helpers already build strong error messages but lose context once they return from module boundaries.
- This is mostly mechanical and reduces risk without changing core refactoring behavior.

## Tradeoffs
- Pros
  - Cleaner control flow and easier testability at boundaries.
  - Better diagnostics (single place to translate failures to user-visible status).
  - Lower chance of masking original failures by repeated wrapping.
- Cons
  - Requires touching many small callsites in `cli.py`.
  - Slightly stricter exception contract can expose previously uncaught edge-case exceptions.

## Estimated phases
1. **Boundary inventory and mapping**
   - Document every `raise SystemExit`, `raise ContinuousRefactorError`, and parser-driven failure path in `cli.py`, `loop.py`, and config helpers.
   - Define the boundary contract: CLI maps to `1/2/130` and loop emits final status strings only.
2. **Loop/domain cleanup**
   - Remove `SystemExit` raises from loop callsites.
   - Return stable result codes and/or raise `ContinuousRefactorError` with context.
   - Keep all existing statuses (`completed`, `failed`, `interrupted`, etc.) unchanged.
3. **CLI boundary translation**
   - Keep `_run_with_loop_errors` as the narrow boundary wrapper and route all loop failures through it.
   - Update helper handlers to raise domain exceptions and let CLI own process exit policy.
4. **Config-path boundary alignment**
   - Normalize project/taste resolution helpers to raise typed `ContinuousRefactorError` only.
   - Keep messages and argument contracts in CLI so user-facing strings remain stable.

## Risk profile
- Risk level: Medium.
- Main risk: accidental behavior change in exit-code semantics for edge cases where callsites currently call `SystemExit(2)` directly.
- Control plan: preserve exact parser/validation outcomes by mapping explicit pathways in small helper layer; avoid touching `routing`, `phases`, or `migrations` behavior.

## Migration footprint
- `src/continuous_refactoring/loop.py`
- `src/continuous_refactoring/cli.py`
- `src/continuous_refactoring/config.py`
