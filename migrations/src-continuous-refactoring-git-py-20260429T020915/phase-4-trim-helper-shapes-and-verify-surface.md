# Phase 4: Trim Helper Shapes and Verify Surface

## Scope
- `src/continuous_refactoring/git.py`
- `tests/test_git.py`
- Optional verification-only coverage in `tests/test_continuous_refactoring.py`
  if package-root export assertions are still missing.

required_effort: low
effort_reason: final cleanup is limited to transitional private helpers and surface verification

## Precondition
Phase 3 is marked complete, and the Phase 1 export-lock coverage that pins the
`src/continuous_refactoring/git.py` `__all__` symbol set still exists as the
artifact this phase will preserve.

## Instructions
- Remove only private helpers or naming that were introduced or retained solely
  to stage phases 2 or 3.
- Inventory private helpers and aliases introduced during phases 2 or 3. Delete
  each one by default unless it is explicitly named in the phase output,
  justified as part of the final `git.py` structure, and covered by focused
  tests.
- Do not reopen module structure or error-boundary design in this phase.
- Verify that `continuous_refactoring.git` and package-root re-export still
  expose the same git helper surface after cleanup.
- If explicit export coverage is still missing, add the smallest assertion set
  that will catch symbol drift.
- If preserving the package-root surface appears to require editing
  `src/continuous_refactoring/__init__.py`, stop and report the contradiction
  instead of widening this phase.

## Definition of Done
- Every private staging helper or alias introduced during phases 2 or 3 has
  been deleted, or is named in the phase output with final-shape justification
  and focused test coverage.
- The public symbol set exposed from `git.py.__all__` is unchanged from the
  symbol set pinned by the Phase 1 export-lock coverage.
- Any package-root re-export coverage needed to catch symbol drift is present.
- The final `git.py` layout and cleanup preserve caller-facing behavior under
  the focused git tests and the configured broad validation command.
- The configured broad validation command passes.

## Validation
- Run `uv run pytest tests/test_git.py`.
- If package-root export coverage is added or changed, run
  `uv run pytest tests/test_continuous_refactoring.py`.
- Finish with `uv run pytest`.
