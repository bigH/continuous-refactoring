# Phase 2: leaf-module-boundary-wrapping

## Objective

Apply causal boundary wrapping inside leaf modules (`agent`, `config`, `artifacts`) so the caller receives meaningful context without mid-stack duplication.

## Scope

- `src/continuous_refactoring/agent.py`
- `src/continuous_refactoring/config.py`
- `src/continuous_refactoring/artifacts.py`

No files outside this migration scope.

## Instructions

1. `src/continuous_refactoring/agent.py`
   1. Wrap process launch / IO boundary operations with `raise ContinuousRefactorError(... ) from error` in all leaf failure points:
      - `run_agent_interactive`
      - `run_agent_interactive_until_settled`
      - `run_observed_command`
   2. Add causal wrapping around:
      - `stdin/stdout/stderr` sink setup (`mkdir`, `open`, `unlink`, `Popen`, timeout/termination wait points where a domain error replaces low-level errors).
   3. Keep message text unchanged except where a boundary context message needs causal nesting.
2. `src/continuous_refactoring/config.py`
   1. Wrap manifest/config boundaries with causal nesting:
      - file read (`Path.read_text`) and JSON parse in manifest loaders.
      - manifest temp-file write/replacement flow in `save_manifest`.
   2. If a low-level `OSError`, `JSONDecodeError`, or `KeyError` is turned into `ContinuousRefactorError`, add `from error`.
   3. Keep `load_manifest`/`save_manifest` observable behavior unchanged (paths and payload structure).
3. `src/continuous_refactoring/artifacts.py`
   1. Keep existing `ValueError` validation boundaries as-is.
   2. Confirm all filesystem-write operations remain in their own module boundary and are either bubbled or wrapped with explicit `from`.

## Ready_when (mechanical)

1. `rg -n "raise ContinuousRefactorError\\(" src/continuous_refactoring/agent.py src/continuous_refactoring/config.py src/continuous_refactoring/artifacts.py` returns only raises that either:
   - come from existing module entry boundaries, and
   - use `from error` when they are produced in an `except` block.
2. In this phase, no `SystemExit`/parser behavior changes are allowed in these files.
3. `git diff --name-only` contains only files in this phase scope.

## Validation

1. Run targeted tests for boundary behavior:
   1. `tests/test_run_observed_command.py` (if available) equivalent command-failure path checks in existing suites.
   2. `tests/test_config.py::test_load_manifest`-family cases.
   3. `tests/test_continuous_refactoring.py` command wrapping cases.
2. Add one assertion pass for each changed leaf wrapper:
   - the raised boundary exception’s `__cause__` is non-`None` when a lower I/O/process error is induced.
3. Ensure success-path tests for touched modules still pass.

