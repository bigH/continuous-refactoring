# Phase 2: loop delegates target parsing and resolution

## Objective
Make `loop.py` a thin orchestration layer by delegating all target argument parsing to `targeting.py`.

## Scope
- `src/continuous_refactoring/targeting.py`
- `src/continuous_refactoring/loop.py`
- `tests/test_run_once_regression.py`
- `tests/test_run.py`

## Instructions
1. Remove local `_parse_paths_arg` path parsing logic from `loop.py`.
2. Update `_resolve_targets_from_args()` to call `targeting.parse_paths_arg(...)` and pass the parsed value directly into `resolve_targets(...)`.
3. Keep existing precedence behavior identical: `targets` > `globs` > `extensions` > `paths` > random.
4. Ensure no behavioral coupling is introduced in loop entrypoints:
   - `run_once()`
   - `run_loop()`
5. Add/adjust regression checks covering:
   - trimmed path handling in the run-once path (`args.paths` with whitespace)
   - path-driven target prompt shape in one-shot flow
   - non-empty target list behavior in normal loop mode.
6. Ensure parse helper ownership is visible at callsite by importing from `continuous_refactoring.targeting` rather than local path parsing implementations.

## Precondition
- `phase-1-targeting-parse-foundation.md` is marked complete in the migration manifest.
- `rg -n \"def parse_paths_arg\\(\" src/continuous_refactoring/targeting.py` finds the parser in `targeting.py`.
- `rg -n \"def _parse_paths_arg\\(\" src/continuous_refactoring/loop.py` finds the local parser that this phase removes.
- `rg -n \"_resolve_targets_from_args\\(\" src/continuous_refactoring/loop.py` finds the shared helper definition plus the existing `run_once()` and `run_loop()` callsites, confirming both entrypoints already route through one resolver before this phase delegates path parsing.

## Definition of Done
- `loop.py` contains no `_parse_paths_arg` implementation and does not parse `args.paths` directly.
- `_resolve_targets_from_args()` passes parsed `paths` and raw non-path selectors to `resolve_targets(...)` in one place.
- `run_once` and `run_loop` behavior stays unchanged for all targeting modes.
- Focused regression scope passes:
  - path trimming in `args.paths` on one-shot path
  - run-loop target prompt shape with non-empty target set
  - precedence still resolves to `targets` > `globs` > `extensions` > `paths` > random.
- `uv run pytest tests/test_targeting.py tests/test_run_once_regression.py tests/test_run.py` passes.
- `rg -n \"parse_paths_arg\\(\" src/continuous_refactoring/loop.py` reports only delegated usage to `targeting.parse_paths_arg`.

## Validation steps
- Run: `uv run pytest tests/test_targeting.py tests/test_run_once_regression.py tests/test_run.py`
- Verify delegation ownership by inspection:
  - `rg -n \"_parse_paths_arg\\(\" src/continuous_refactoring/loop.py`
  - `rg -n \"parse_paths_arg\\(\" src/continuous_refactoring/loop.py`
- Keep `tests/test_run_once_regression.py` and `tests/test_run.py` green before phase transition.
