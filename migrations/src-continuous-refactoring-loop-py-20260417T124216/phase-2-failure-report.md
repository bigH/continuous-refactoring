# Phase 2 — Extract `failure_report.py`

## Goal

Move reason-for-failure document writing and decision persistence out of
`loop.py` into `src/continuous_refactoring/failure_report.py`. Owns the
failure-doc format end-to-end so future format changes stop churning `loop.py`.

**Blocked by:** phase 1 (imports `decisions.DecisionRecord`, etc).

## Scope — Symbols to Move

From `loop.py` to `failure_report.py`:

- `_write_reason_for_failure` → `write` (public; module FQN becomes `failure_report.write`)
- `_next_step_text` → `next_step_text` (public — called externally? verify; if only used inside module, keep `_next_step_text`)
- `_yaml_scalar` → stays private: `_yaml_scalar`
- `_persist_decision` → `persist_decision` (public)
- `_effective_record` → `effective_record` (public)
- `_relative_path` → stays private: `_relative_path` (utility)

## Out of Scope

- Routing/migration-tick symbols — phase 3.
- `_retry_context` — stays in `loop.py` through phase 3; revisited in phase 4.

## Instructions

1. Create `src/continuous_refactoring/failure_report.py`. One-line module docstring.
2. Move the listed symbols. Update imports inside the new module to pull types
   from `continuous_refactoring.decisions` (phase 1 placed them there).
3. In `loop.py`, replace the moved definitions with
   `from continuous_refactoring.failure_report import write as write_failure_report, persist_decision, effective_record`.
   (Alias at import site, not a re-export.)
4. Update `src/continuous_refactoring/artifacts.py` or any other caller if it
   reaches into these symbols. Grep: `_write_reason_for_failure`,
   `_persist_decision`, `_effective_record`.
5. Update test monkeypatch paths pointing at
   `continuous_refactoring.loop._write_reason_for_failure` /
   `_persist_decision` to the new FQN.
6. Add `tests/test_failure_report.py`:
   - Property tests for `_yaml_scalar`: round-trips through `yaml.safe_load`
     for `str | int | float | bool | None`; output never introduces a control
     character; multi-line strings use block-style correctly.
   - Example test for `write`: given a fixed `DecisionRecord`, writes a file
     whose parsed YAML header matches expected fields. Use a real `tmp_path`,
     no mocks.
   - Example test for `persist_decision`: writes JSON record to artifacts dir
     with expected schema.

## Precondition

`phase-1-decisions.md` is complete so `decisions.py` symbols are already at their final FQNs.

## Definition of Done

- `failure_report.py` exists and owns reason-doc + persistence logic.
- `loop.py` no longer defines `_write_reason_for_failure`, `_persist_decision`,
  `_yaml_scalar`, `_effective_record`, `_next_step_text`, `_relative_path`.
- `tests/test_failure_report.py` exists with at least one property test on
  `_yaml_scalar` and one example test per public function.
- `grep -rn "loop\._\(write_reason_for_failure\|persist_decision\|yaml_scalar\|effective_record\)" src tests` — empty.
- `pytest` green.
- `loop.py` down another ~200–300 lines; `failure_report.py` in 200–350 lines.

## Validation Steps

1. `pytest -x`
2. `python -m continuous_refactoring --help`
3. Smoke run: trigger a failing-path refactor in a tmp fixture, confirm the
   reason-for-failure doc is written and parses as valid YAML.
4. `grep -rn "continuous_refactoring\.loop\._write_reason_for_failure\|continuous_refactoring\.loop\._persist_decision" src tests` — empty.

## Risk & Rollback

Moderate: touches filesystem-writing code. Property tests on YAML scalar
escaping are the safety net — they must be added in this phase, not deferred.
Rollback: `git reset --hard HEAD~1`.
