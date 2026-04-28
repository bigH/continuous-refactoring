# Phase 3: boundary smoke checks and migration-contract stabilization

## Objective
Validate that tightened command-boundary translation does not alter orchestration behavior and that phase docs match the lived contract.

## Scope
- `src/continuous_refactoring/loop.py`
- `src/continuous_refactoring/phases.py`
- `src/continuous_refactoring/prompts.py`
- `src/continuous_refactoring/config.py`
- `src/continuous_refactoring/artifacts.py`
- `src/continuous_refactoring/__init__.py`
- `tests/test_scope_loop_integration.py`
- `tests/test_loop_migration_tick.py`
- `tests/test_git.py`

## Instructions
1. Do not change orchestration behavior or control flow in `loop.py`, `phases.py`, or `prompts.py`.
2. Keep migration metadata behavior stable in `config.py` and `artifacts.py`.
3. Keep package export behavior unchanged in `__init__.py` except for expected automatic re-export of `GitCommandError`.
4. Run targeted integration tests that exercise command execution paths used around plan execution and migration ticks.
5. Leave only migration documentation updates if the `Definition of Done` language needs wording alignment after the boundary hardening.

## Precondition
- Phase 2 is complete and `tests/test_git.py` passes.
- Working tree is clean and stable for broader validation.

## Definition of Done
- Targeted integration tests touching `loop`/`phases` command boundaries pass.
- No behavior change in existing migration flow can be observed outside `git.py`.
- Phase file contract is still aligned with execution and prompt wiring.
- `uv run pytest` passes.

## Validation steps
- Run `uv run pytest tests/test_scope_loop_integration.py tests/test_loop_migration_tick.py`.
- Run `uv run pytest tests/test_git.py`.
- Run `uv run pytest`.
