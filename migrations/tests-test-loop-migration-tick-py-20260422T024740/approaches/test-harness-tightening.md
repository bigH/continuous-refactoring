# Test Harness Tightening

## Strategy

Keep the production migration tick behavior intact and refactor the tests around it. The current `tests/test_loop_migration_tick.py` reads as a mini framework: manifest construction, live-dir patching, readiness stubs, execution stubs, classifier traps, and one-shot agent stubs are all mixed into each test. Consolidate that setup into a small, typed test harness so each test states only the scenario and expected outcome.

The production code changes should be limited to small truthfulness fixes discovered while cleaning the tests, such as naming helpers around phase-file labels or exposing an existing domain helper that removes brittle test monkeypatching. Do not reshape `loop.py` or routing ownership in this approach.

## What Changes

- Introduce a local `MigrationTickHarness` in `tests/test_loop_migration_tick.py`, or a shared helper in `tests/conftest.py` only if `tests/test_focus_on_live_migrations.py` can use it without becoming less clear.
- Replace scattered `_patch_*` helpers with scenario methods like `given_ready_phase`, `given_deferred_phase`, `trap_classifier`, and `run_once`.
- Keep assertions outcome-based: manifest state, classifier fallthrough, commit labels, output, and raised boundary errors.
- Remove decorative section comments once test names and harness methods carry the structure.
- Optionally move duplicated manifest builders between `test_loop_migration_tick.py` and `test_focus_on_live_migrations.py` into one shared helper if the call sites get shorter, not just different.

## Estimated Phases

1. Characterize current test scenarios and introduce the harness without changing assertions.
2. Migrate existing tests onto the harness, deleting redundant helpers as each scenario moves.
3. Prune duplication with `test_focus_on_live_migrations.py` only where the shared abstraction is obviously clearer.
4. Run narrow and full validation, then make any small naming cleanup that the tests expose.

## Tradeoffs

- Lowest production risk; most changes stay in tests.
- Improves readability of the target file quickly.
- Does not address the source-level split between `loop.py`, `routing_pipeline.py`, `migrations.py`, and `phases.py`.
- Shared test helpers can become their own abstraction tax if pushed into `conftest.py` too early.

## Risk Profile

Low. The main risk is accidentally making the tests more abstract than the behavior they protect. Keep the harness concrete and scenario-oriented. Avoid mocks that assert internals unless they protect routing boundaries already encoded by the current tests, such as "classifier is not called during migration tick."

## Validation

- `uv run pytest tests/test_loop_migration_tick.py`
- `uv run pytest tests/test_focus_on_live_migrations.py tests/test_scope_loop_integration.py`
- `uv run pytest`

## Fit With Taste

This fits the taste when the goal is readability and validation safety. It prefers real outcomes, deletes helper clutter, and avoids a speculative source split. It is the safest choice if the migration is meant to improve the selected test without committing to architecture work.
