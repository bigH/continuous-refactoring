# Phase 1 — Extract `decisions.py`

## Goal

Move pure status/decision types and parsing out of `loop.py` into a new
`src/continuous_refactoring/decisions.py`. Zero behavior change; pure relocation
plus focused parser tests that stay within the repo's stdlib-only test setup.

## Scope — Symbols to Move

From `loop.py` to `decisions.py`:

- `AgentStatus` (dataclass, ~line 139)
- `DecisionRecord` (dataclass, ~line 151)
- `RunnerDecision`, `RetryRecommendation`, `RouteOutcome` — if defined alongside (verify; move any enum-like status types)
- `_parse_agent_status_block` → rename to `parse_status_block` (public)
- `_read_agent_status` → rename to `read_status` (public — it's the module's read surface)
- `_status_path_text` → stays private: `_status_path_text`
- `_sanitize_text` → `sanitize_text` (public)
- `_status_summary` → `status_summary` (public)
- `_resolved_phase_reached` → `resolved_phase_reached` (public)
- `_error_failure_kind` → `error_failure_kind` (public)
- `_default_retry_recommendation` → `default_retry_recommendation` (public)

Keep in `loop.py`: `_retry_context` (uses `DecisionRecord` but is orchestration
glue — it stays until phase 4 revisits).

## Out of Scope

- `_write_reason_for_failure`, `_persist_decision`, `_yaml_scalar`,
  `_effective_record`, `_relative_path`, `_next_step_text` — phase 2.
- Any routing/pipeline symbols — phase 3.

## Instructions

1. Create `src/continuous_refactoring/decisions.py`. Module docstring: one line,
   "Agent status types and decision records."
2. Move the listed symbols verbatim. Rename per the list above.
3. Update imports inside `loop.py` to `from continuous_refactoring.decisions import ...`.
4. Update every other importer across `src/` and `tests/` to the new FQN. Grep
   for each moved symbol name to catch stragglers.
5. Update `tests/conftest.py` and any test using
   `monkeypatch.setattr("continuous_refactoring.loop.<moved_symbol>", ...)` to
   point at `continuous_refactoring.decisions.<new_name>`.
6. Add `tests/test_decisions.py` with focused stdlib-only tests:
   - `parse_status_block` invariants: table-driven cases plus a small
     stdlib-generated corpus that never raises on arbitrary text; returns
     `None` iff no recognizable header; parsed fields match current behavior.
   - `sanitize_text`: idempotent; never expands length beyond a bound tied to
     repo_root substitution; returns `None` iff input is `None`.
   - `error_failure_kind`: total over `str`; output is one of the known kinds.
7. Do not add a re-export in `loop.py`. Tests and callers use the new FQN.

## Ready When

- `src/continuous_refactoring/decisions.py` exists and contains every listed symbol.
- `loop.py` no longer defines any of the moved symbols.
- `grep -rn "loop\.\(AgentStatus\|DecisionRecord\|_parse_agent_status_block\|_sanitize_text\|_status_summary\|_resolved_phase_reached\|_error_failure_kind\|_default_retry_recommendation\|_read_agent_status\)" src tests` returns nothing.
- `tests/test_decisions.py` exists with focused stdlib-only coverage for each moved pure function listed above.
- `pytest` is green.
- `python -m continuous_refactoring --help` runs without error.
- `loop.py` dropped by ~250–350 lines; `decisions.py` is 200–350 lines.

## Validation Steps

1. `pytest -x`
2. `python -m continuous_refactoring --help`
3. `grep -rn "continuous_refactoring\.loop\.\(AgentStatus\|DecisionRecord\)" src tests` — expect empty.
4. `wc -l src/continuous_refactoring/loop.py src/continuous_refactoring/decisions.py` — confirm size targets.
5. Smoke: `python -m continuous_refactoring run-once --help` exits 0.

## Risk & Rollback

Lowest-risk phase. If validation fails, `git reset --hard HEAD~1` on the branch
and re-do. No DB / external state.
