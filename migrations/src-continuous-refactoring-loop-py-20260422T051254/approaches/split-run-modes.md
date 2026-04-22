# Split Run Modes

## Strategy

Split the three command modes into dedicated driver modules:

- `src/continuous_refactoring/run_once.py`
  - one-shot target selection
  - one agent call, no fix retry
  - validation and diffstat printing
- `src/continuous_refactoring/run_loop.py`
  - normal multi-target loop
  - retry/fix-prompt behavior
  - baseline checks and consecutive-failure policy
- `src/continuous_refactoring/migrations_loop.py`
  - focused live-migration loop
  - eligibility polling and tick sleep behavior

Leave `loop.py` either deleted or reduced to a real shared module only if it still owns meaningful loop-neutral behavior. Do not keep a re-export facade; update `cli.py`, tests, and `__init__.py` to import from the new modules directly.

This approach treats command modes as the useful FQNs. A reader looking for `continuous_refactoring.run_loop.run_loop()` gets the exact behavior behind the CLI command instead of a catch-all file.

## Tradeoffs

Pros:
- Strongest readability gain at call sites and stack traces.
- Removes the current "everything driver-ish lives in loop.py" bucket.
- Makes each mode easier to evolve independently, especially `run-once`, which intentionally does not use the fix-retry path.
- Helps tests become more mode-focused.

Cons:
- Higher churn than extracting attempt logic alone.
- Some helpers are genuinely shared: `_effective_max_attempts()`, target resolution, taste loading, baseline checks, commit finalization, and sleep logging. They need a clean home, not copy/paste.
- Public package exports and CLI imports must move in one commit because this repo forbids re-export shims.
- Many monkeypatch paths in tests reference `continuous_refactoring.loop.*`.

## Estimated Phases

1. **Map mode-local and shared code**
   - Classify every helper in `loop.py` as run-once only, normal-loop only, focused-migration only, or shared.
   - Write the intended destination list into the phase doc before moving code.

2. **Extract shared driver support**
   - Create a small `driver_support.py` or similarly domain-named module for taste loading, max-attempt normalization, target parsing, baseline checks, sleeping, and commit finalization.
   - Keep this module boring and concrete. No generic runner framework.

3. **Move `run_once()`**
   - Create `run_once.py`.
   - Update `cli.py`, `__init__.py`, and run-once tests.
   - Validation: `uv run pytest tests/test_run_once.py tests/test_run_once_regression.py tests/test_e2e.py`.

4. **Move `run_loop()`**
   - Create `run_loop.py`.
   - Move retry orchestration and ordinary target iteration.
   - Update tests that patch normal-loop internals.
   - Validation: `uv run pytest tests/test_run.py tests/test_no_driver_branching.py`.

5. **Move focused migration loop**
   - Create `migrations_loop.py`.
   - Move `_focus_eligible_manifests()` and `run_migrations_focused_loop()`.
   - Validation: `uv run pytest tests/test_focus_on_live_migrations.py tests/test_loop_migration_tick.py`.

6. **Delete or shrink `loop.py`**
   - Delete it if empty.
   - If it remains, it must own a real concept and have no compatibility exports.
   - Run `uv run pytest`.

## Risk Profile

Medium-high. The intended end state is clean, but the blast radius is broad because `loop.py` is imported by CLI, package re-export, and many tests.

Main watch-outs:
- Package uniqueness in `__init__.py`: moved functions must be exported from exactly one module.
- Existing tests use monkeypatch paths as part of their harness. Update deliberately rather than preserving stale paths.
- Do not collapse `run_once()` into the retryable attempt path unless tests prove the one-shot semantics remain exact.
- Keep no-branching behavior intact: the driver still creates local commits only and never switches branches.

## Best Fit

Choose this if the desired migration outcome is better module names and command-mode ownership. It is too much for a quick safety refactor, but it is the cleanest long-term file shape.
