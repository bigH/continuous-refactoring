# Phase 2 — Extract `failure_report.py`

## Goal

Move failure-snapshot writing and decision-persistence helpers out of `loop.py`
into `src/continuous_refactoring/failure_report.py`.

This phase is a **pure relocation plus focused tests**. No format redesign, no
behavior change, and no routing work.

**Blocked by:** phase 1 (`decisions.py` provides the stable `DecisionRecord`
FQN used here).

## Scope — Symbols to Move

From `loop.py` to `failure_report.py`:

- `_write_reason_for_failure` → `write` (public)
- `_persist_decision` → `persist_decision` (public)
- `_effective_record` → `effective_record` (public)
- `_next_step_text` → stays private: `_next_step_text`
- `_yaml_scalar` → stays private: `_yaml_scalar`
- `_relative_path` → stays private: `_relative_path`

Keep in `loop.py`:

- `_retry_context`
- `_run_refactor_attempt`
- all routing / migration-tick helpers (phase 3)
- entrypoints and commit orchestration

## Out of Scope

- Any routing or scope-expansion symbol.
- Any new extraction beyond the helpers listed above.
- Changing the failure snapshot schema or text layout.

## Instructions

1. Create `src/continuous_refactoring/failure_report.py` with a one-line module
   docstring.
2. Move the listed helpers verbatim, keeping private helpers private inside the
   new module.
3. Import `DecisionRecord` from `continuous_refactoring.decisions`.
4. Update `loop.py` to import only the public surface it still uses:
   `effective_record` and `persist_decision`.
5. Update any tests or monkeypatches that still point at
   `continuous_refactoring.loop._persist_decision` or
   `continuous_refactoring.loop._effective_record`.
6. Add `tests/test_failure_report.py` with **stdlib-only** coverage for:
   - `effective_record` exhausting `--max-attempts`
   - representative `_yaml_scalar` escaping/quoting cases (`None`, `bool`,
     `int`, plain strings, multiline strings, quotes/backslashes)
   - `write` emitting the expected snapshot header/body fields for a fixed
     `DecisionRecord`
   - `persist_decision` commit vs. non-commit behavior

## Precondition

`phase-1-decisions.md` is complete.

## Definition of Done

- `src/continuous_refactoring/failure_report.py` exists and owns the moved
  helpers.
- `loop.py` no longer defines `_write_reason_for_failure`, `_persist_decision`,
  `_effective_record`, `_next_step_text`, `_yaml_scalar`, or `_relative_path`.
- `tests/test_failure_report.py` exists and uses only the stdlib + pytest.
- `grep -rn "loop\._\(write_reason_for_failure\|persist_decision\|effective_record\|next_step_text\|yaml_scalar\|relative_path\)" src tests` returns nothing.
- `uv run pytest` is green.
- `loop.py` drops by roughly 150–220 lines; `failure_report.py` lands roughly
  in the 170–260 line range.

## Validation Steps

1. `uv run pytest tests/test_failure_report.py tests/test_run.py tests/test_run_once.py`
2. `uv run pytest`
3. `python -m continuous_refactoring --help`
4. `grep -rn "continuous_refactoring\.loop\._write_reason_for_failure\|continuous_refactoring\.loop\._persist_decision\|continuous_refactoring\.loop\._effective_record" src tests` — expect empty.
5. `wc -l src/continuous_refactoring/loop.py src/continuous_refactoring/failure_report.py`

## Risk & Rollback

Moderate: touches filesystem-writing and artifact-persistence code. The safety
net is focused stdlib-only testing of the existing format and max-attempts
behavior. Rollback: `git reset --hard HEAD~1`.
