# Phase 4 — Trim `loop.py`

## Goal

Clean up `loop.py` now that its three domains have moved. Confirm `run_once`
and `run_loop` read top-to-bottom as orchestration, with private helpers
grouped directly below their caller.

**Blocked by:** phase 3.

## Scope

No new modules. No behavior change. Pure tidy:

1. Remove any `from continuous_refactoring.loop import ...` dead imports in
   other files (they should all be gone already — verify).
2. Consolidate the remaining imports at the top of `loop.py`. Group by stdlib
   / third-party / internal, alphabetical within each.
3. Delete unused names, constants, or helpers that phases 1–3 orphaned.
   Candidates to check: `_sanitize_text` references, `_relative_path` import
   aliases, anything imported but unused.
4. Reorder top-level definitions so `run_once` and `run_loop` sit near the top
   (after arg helpers and `run_baseline_checks`), and `_run_refactor_attempt`
   + `_finalize_commit` directly below their sole caller.
5. Re-examine `_retry_context`: if it only decorates a `DecisionRecord` for
   display, move it to `decisions.py` as `retry_context`. Otherwise leave.
6. Scan for stale comments left over from pre-split `loop.py`; delete any
   that reference symbols now in other modules. Taste: comments near zero.
7. Confirm `loop.py` final size is in the 400–550 line range. If above 600,
   identify what else should have moved and flag for a follow-up (do not do
   a fifth extraction in this phase).

## Out of Scope

- Any new extraction. If something looks extractable, file a follow-up note
  in `migrations/.../followups.md` rather than expanding phase 4.
- `unify-run-once-and-loop` refactor — separate migration, as the approach
  doc says.

## Instructions

1. Start on a clean branch at phase-3 HEAD. `pytest` green.
2. Apply the trim steps above as a single commit.
3. Re-read `run_once` top-to-bottom, then `run_loop`. Each should fit on
   one screen's worth of scanning without jumping into out-of-order helpers.
4. If `_retry_context` moved, add an example test in `tests/test_decisions.py`.

## Ready When

- `loop.py` is 400–550 lines.
- Top of `loop.py` shows: imports → arg helpers → `run_baseline_checks` →
  `run_once` → `run_loop` → private helpers.
- No unused imports (run `ruff check` if configured; otherwise grep
  each imported name).
- No comment in `loop.py` references a symbol that now lives elsewhere.
- `pytest` green.
- `python -m continuous_refactoring run-once` works end-to-end on a fixture.

## Validation Steps

1. `pytest -x`
2. `python -m continuous_refactoring --help`
3. `python -m continuous_refactoring run-once --help`
4. Full E2E: `pytest tests/test_e2e.py tests/test_scope_loop_integration.py`
5. `wc -l src/continuous_refactoring/*.py` — confirm size distribution:
   `loop.py` 400–550, `decisions.py` 200–350, `failure_report.py` 200–350,
   `routing_pipeline.py` 300–450.
6. Import check: `python -c "from continuous_refactoring.loop import run_once, run_loop; print('ok')"`.

## Risk & Rollback

Lowest-risk phase (no moves, only tidy). Rollback: `git reset --hard HEAD~1`.
