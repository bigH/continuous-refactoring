# Phase 4 — Trim `loop.py`

## Goal

Clean up `loop.py` after phases 2 and 3 land so the file reads as a clearer
orchestration module.

This phase is **cleanup only**: no new modules, no new extraction campaign, and
no attempt to force `loop.py` down to ~500 lines.

**Blocked by:** phases 2 and 3.

## Scope

Pure tidy work only:

1. Remove dead imports and stale aliases in `loop.py` and in any callers that
   still import moved symbols from `loop.py`.
2. Group and reorder the remaining imports and top-level helpers for readability.
3. Delete comments or prose that still refer to helpers now owned by
   `decisions.py`, `failure_report.py`, or `routing_pipeline.py`.
4. Keep `_retry_context`, `_run_refactor_attempt`, the entrypoints, and commit
   plumbing in `loop.py`. If those still look extractable, capture that as
   follow-up work rather than expanding phase 4.
5. Confirm the post-cleanup size is realistic for a no-new-extraction pass:
   roughly **950–1100 lines**.

## Out of Scope

- Any additional extraction whose main purpose is line-count reduction.
- Moving `_retry_context` to another module.
- Chasing the old ~500-line target inside this phase.
- `unify-run-once-and-loop` refactors.

## Instructions

1. Start from a head where phases 2 and 3 are both landed and `uv run pytest`
   is already green.
2. Apply only cleanup/reordering/deletion work.
3. Re-read `run_once`, `run_loop`, and `run_migrations_focused_loop` after the
   cleanup so their surrounding helper layout is easy to follow.
4. If additional extraction still feels necessary after the tidy pass, record it
   in the plan or a follow-up note instead of silently widening this phase.

## Precondition

`phase-2-failure-report.md` and `phase-3-routing-pipeline.md` are complete.

## Definition of Done

- `loop.py` no longer contains dead imports, stale aliases, or comments that
  refer to moved helpers as if they still lived in `loop.py`.
- No caller still imports moved phase-2/phase-3 symbols from `loop.py`.
- `uv run pytest` is green.
- `python -m continuous_refactoring --help` works.
- `loop.py` ends this phase roughly in the 950–1100 line range. A lower number
  is fine; ~500 is explicitly out of scope for this phase.
- The migration docs still tell the truth about the remaining gap to any future
  ~500-line target.

## Validation Steps

1. `uv run pytest`
2. `python -m continuous_refactoring --help`
3. `python -m continuous_refactoring run-once --help`
4. `uv run pytest tests/test_run.py tests/test_run_once.py tests/test_scope_loop_integration.py tests/test_focus_on_live_migrations.py`
5. `wc -l src/continuous_refactoring/loop.py src/continuous_refactoring/decisions.py src/continuous_refactoring/failure_report.py src/continuous_refactoring/routing_pipeline.py`
6. `python -c "from continuous_refactoring.loop import run_once, run_loop; print('ok')"`

## Risk & Rollback

Lowest-risk remaining phase. If the cleanup starts to require another major
symbol move, stop and spin that into a follow-up migration instead. Rollback:
`git reset --hard HEAD~1`.
