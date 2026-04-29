# Phase 1: Lock Current Surface

## Scope
- `tests/test_migrations.py`
- `src/continuous_refactoring/migrations.py`
- If needed for focused regression coverage only:
  `tests/test_continuous_refactoring.py`, `tests/test_phases.py`,
  `tests/test_planning.py`, `tests/test_prompts.py`, `tests/test_wake_up.py`

required_effort: low
effort_reason: behavior-locking test work is local and should stay cheap

## Precondition
This migration is still in planning or at its first executable phase, and
`src/continuous_refactoring/migrations.py` still contains the shipped manifest
types, manifest I/O helpers, and exported operational helpers that later phases
intend to split.

## Instructions
- Add or tighten regression tests for the public
  `continuous_refactoring.migrations` surface that later phases must preserve.
- Lock the exported-symbol contract explicitly. The regression coverage must
  name the compatibility export set that stays publicly reachable from
  `continuous_refactoring.migrations`, not just assert that some representative
  imports still work.
- Cover behavior that would be easy to break during the split:
  current-phase lookup, cursor advancement, phase completion/reset behavior,
  eligibility logic, and manifest load/save error wrapping.
- Favor outcome-based tests over call-shape assertions.
- Keep production edits minimal in this phase. Only change source if a tiny fix
  is required to expose or stabilize the behavior being locked down.

## Definition of Done
- `tests/test_migrations.py` or equivalent focused regression coverage names the
  shipped compatibility export set for `continuous_refactoring.migrations`.
- The public helpers and value types that later phases rely on are protected by
  explicit regression coverage.
- The test suite would catch export drift, operational-behavior regressions, and
  broken boundary error nesting introduced by the module split.
- No user-visible contract has changed; this phase only strengthens the safety
  net.
- The configured broad validation command passes.

## Validation
- Run the narrowest relevant checks first, expected to include
  `uv run pytest tests/test_migrations.py`.
- If the export-contract coverage lives in package-root tests, run the focused
  follow-up checks such as `uv run pytest tests/test_continuous_refactoring.py`.
- If new regression coverage touches import-heavy callers, run the relevant
  focused checks such as `uv run pytest tests/test_phases.py
  tests/test_planning.py tests/test_prompts.py tests/test_wake_up.py`.
- Finish with `uv run pytest`.
