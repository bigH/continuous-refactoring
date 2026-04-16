# Phase 3 — Orchestration and CLI contract alignment

## Scope (hard allowed set)

1. `src/continuous_refactoring/loop.py`
2. `src/continuous_refactoring/cli.py`
3. `src/continuous_refactoring/__init__.py` (only if export list must stay coherent after phase-2 edits)

No edits in core boundary modules (`artifacts.py`, `agent.py`, `config.py`, `git.py`, `targeting.py`) in this phase.

## Goal

Move to a single boundary translation at orchestration/user edges so lower-layer causal errors are preserved and not re-wrapped.

## Detailed instructions

1. In `loop.py`, keep orchestration-level behavior unchanged and avoid replacing lower-level `ContinuousRefactorError` messages except for necessary boundary context.
2. In `cli.py`, preserve existing `SystemExit` conversion flow while ensuring wrapped errors carry causal chains when user boundary requires conversion.
3. Remove duplicate message-only wrapping where `ContinuousRefactorError` already has a meaningful chain.
4. Keep migration-state names and terminal output strings unchanged.
5. Keep imports and exports stable unless required by explicit API changes from phase 2.

## Ready when (machine-checkable)

1. `uv run pytest tests/test_run_once.py::test_run_once_validation_gate`
2. `uv run pytest tests/test_run_once.py::test_run_once_no_fix_retry`
3. `uv run pytest tests/test_run_once.py::test_run_once_prints_branch_and_diff tests/test_run_once.py::test_run_once_prints_and_records_commit`
4. `uv run pytest tests/test_loop_migration_tick.py::test_eligible_ready_migration_advances_phase`
5. `uv run pytest tests/test_run_once.py::test_run_once_uses_default_prompt`
6. `uv run pytest tests/test_run.py::test_run_pushes_after_commit tests/test_run.py::test_run_no_push_flag`
7. `uv run pytest tests/test_run.py::test_cli_errors_when_no_targets_and_no_scope_instruction`
8. `git diff --name-only -- src/continuous_refactoring/loop.py src/continuous_refactoring/cli.py src/continuous_refactoring/__init__.py` includes only listed files.

## Validation

1. CLI and loop behavior remains equivalent on success paths and output-sensitive fixtures.
2. `ContinuousRefactorError` objects are not wrapped away at both `loop` and `cli` boundaries.
3. Migration transition states (`completed`, `failed`, `interrupted`) still occur with existing test observability.
