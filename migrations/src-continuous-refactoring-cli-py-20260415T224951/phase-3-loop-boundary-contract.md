# Phase 3: loop-boundary-contract

## Objective

Normalize loop-owned exception boundaries in `run_once`/`run_loop` so low-level leaf errors are wrapped once, causally, and translated to stable loop status values.

## Scope

- `src/continuous_refactoring/loop.py`

## Instructions

1. Audit and normalize loop entry/exit boundaries:
   1. `run_once`
   2. `run_loop`
   3. helper paths that propagate out as loop failure outcomes (`_route_and_run`, `_try_migration_tick`).
2. For each boundary translation in loop:
   1. keep semantics unchanged,
   2. preserve existing failure path status values (`failed`, `baseline_failed`, `migration_failed`, `max_consecutive_failures`),
   3. add explicit `from` chaining when a new `ContinuousRefactorError` replaces a caught exception.
3. Introduce a loop-local helper for "safe rethrow with context" when needed so callers do not duplicate wrapping:
   - e.g., `raise ContinuousRefactorError("...") from error` only at the loop boundary.
4. Keep orchestration flow identical:
   1. targeting,
   2. branch handling,
   3. attempt loops,
   4. commit/finalize behavior.
5. Do not alter command parsing, scoring, or artifact formatting.

## Ready_when (mechanical)

1. In `src/continuous_refactoring/loop.py`, every `raise ContinuousRefactorError(... )` that occurs inside an `except` has `from <error>`.
2. `git diff --name-only` contains only `src/continuous_refactoring/loop.py`.
3. `phase-2` note map is no longer blocking loop ownership:
   - `phase-1-boundary-contract-audit-notes.json` has at least one unresolved `loop` edge before this phase and none after this phase for implemented edges.

## Validation

1. Run loop-focused tests from this path only:
   1. `tests/test_loop_migration_tick.py`
   2. `tests/test_run_once.py`
   3. `tests/test_run.py`
2. Confirm one test path checks that a boundary failure in loop has a preserved cause chain (`exc.__cause__` not `None`).
3. Confirm no status/branching regressions:
   - successful `run_once` and `run_loop` control flow remains unchanged,
   - unchanged `final_status` on completion/failure categories.

