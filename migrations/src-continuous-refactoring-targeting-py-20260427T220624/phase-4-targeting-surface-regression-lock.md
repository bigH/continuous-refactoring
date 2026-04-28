# Phase 4: targeting surface regression lock

## Objective
Lock in regression coverage across CLI, loop, and planning surfaces after in-place targeting refactor.

## Scope
- `tests/test_targeting.py`
- `tests/test_run.py`
- `tests/test_run_once_regression.py`
- `tests/test_scope_loop_integration.py`
- `tests/test_focus_on_live_migrations.py`
- `tests/test_e2e.py`

## Instructions
1. Run focused integration/reuse tests that depend on targeting contracts (prompt construction, CLI handling, loop flow).
2. Confirm no implicit behavior shift for these invariants:
   - precedence remains `targets > globs > extensions > paths > random`
   - `--paths` whitespace is ignored after parsing
   - random fallback to `general refactoring` remains unchanged when no tracked matches exist
   - no regression in live-migration routing where target files are forwarded unchanged.
3. If new regression failures appear, contain them in a minimal additional test under the targeting module or affected loop integration test in the same phase.
4. Keep user-facing output and validation contracts intact:
   - prompt text/contents used by `compose_full_prompt` flows
   - scope-fallback and max-target behavior semantics.

## Precondition
- Phases 1, 2, and 3 are marked complete in the migration manifest.
- `rg -n \"parse_paths_arg\\(\" src/continuous_refactoring/loop.py` shows only callsite usage from `targeting`.
- `rg -n \"_parse_paths_arg\\(\" src/continuous_refactoring/loop.py` returns no matches.

## Definition of Done
- Focused cross-surface targeting regression suite for this phase passes.
- Targeting behavior is stable for both one-shot and loop runs, including live-migration integration points.
- No behavior contract changes are introduced by module boundary refactoring.
- `uv run pytest tests/test_targeting.py tests/test_run_once_regression.py tests/test_run.py tests/test_scope_loop_integration.py tests/test_focus_on_live_migrations.py tests/test_prompts.py tests/test_prompts_scope_selection.py tests/test_e2e.py` passes.
- `uv run pytest` passes (final migration-wide regression gate).
- In `prompt` and `cli` surfaces, precedence and fallback invariants are still observable:
  - `targets` > `globs` > `extensions` > `paths` > `random`
  - `--paths` whitespace is ignored
  - random fallback still uses existing fallback prompt behavior.

## Validation steps
- Run: `uv run pytest tests/test_targeting.py tests/test_run_once_regression.py tests/test_run.py tests/test_scope_loop_integration.py tests/test_focus_on_live_migrations.py tests/test_prompts.py tests/test_prompts_scope_selection.py tests/test_e2e.py`
- Run: `uv run pytest`
