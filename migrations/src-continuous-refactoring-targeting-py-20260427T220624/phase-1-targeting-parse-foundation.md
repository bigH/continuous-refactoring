# Phase 1: targeting parse foundation

## Objective
Move path and selection parsing into `targeting.py` without changing public targeting output.

## Scope
- `src/continuous_refactoring/targeting.py`
- `tests/test_targeting.py`

## Instructions
1. In `targeting.py`, add a helper that owns CLI path parsing:
   - `parse_paths_arg(raw_paths: str | None) -> tuple[str, ...] | None`
2. Keep `resolve_targets()` as the public entrypoint and route all CLI path parsing through the helper:
   - normalize and drop empty segments in one place.
   - avoid changing output ordering or `Target.provenance` behavior.
3. Add/adjust tests in `tests/test_targeting.py` for:
   - trimming and dropping empty path segments (e.g. `"src/foo.py: src/bar.py"`)
   - `None`/blank path raw values produce `None`
   - precedence expectations preserved in `resolve_targets` when path input is present
4. Keep warning text and exception behavior stable unless a test in this phase requires a deliberate, documented assertion.

## Precondition
- `uv run pytest tests/test_targeting.py` passes on the current state.
- `rg -n \"def _parse_paths_arg\\(|parse_paths_arg\\(\" src/continuous_refactoring/loop.py` returns no matches before edits.
- `rg -n \"def parse_paths_arg\\(\" src/continuous_refactoring/targeting.py` returns no matches before edits.

## Definition of Done
- `targeting.py` has a first-class path parser used by targeting logic (not `loop.py`).
- `tests/test_targeting.py` contains targeted regression coverage for path parsing semantics and precedence at the unit level.
- `uv run pytest tests/test_targeting.py` passes with no skipped assertions specific to this migration.
- No external API/CLI contract changes outside `targeting.py` behavior.
- No local path parsing implementation is introduced in `loop.py` during this phase.

## Validation steps
- Run: `uv run pytest tests/test_targeting.py`
- Validate ownership by inspection and signature checks:
  - `rg -n \"def parse_paths_arg\\(\" src/continuous_refactoring/targeting.py`
  - `rg -n \"def _parse_paths_arg\\(\" src/continuous_refactoring/loop.py`
- Confirm no parse helper is called from `loop.py`:
  - `rg -n \"parse_paths_arg\\(|_parse_paths_arg\\(\" src/continuous_refactoring/loop.py`
