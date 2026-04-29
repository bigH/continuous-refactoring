# Phase 4: Trim Helper Shapes and Verify Surface

## Scope
- `src/continuous_refactoring/git.py`
- `tests/test_git.py`
- If package-root export checks are needed:
  - `src/continuous_refactoring/__init__.py`
  - `tests/test_continuous_refactoring.py`

required_effort: low
effort_reason: final cleanup is limited to transitional private helpers and
surface verification

## Precondition
Phase 3 is marked complete, and the public symbol set in
`src/continuous_refactoring/git.py::__all__` still matches the surface this
migration is preserving.

## Instructions
- Remove only private helpers or naming that were introduced or retained solely
  to stage phases 2 or 3.
- If phases 2 or 3 introduced a private staging helper or alias that did not
  exist at migration start, either delete it here or explicitly keep it by
  folding it into the final `git.py` structure and covering the retained shape
  with focused tests.
- Do not reopen module structure or error-boundary design in this phase.
- Verify that `continuous_refactoring.git` and package-root re-export still
  expose the same git helper surface after cleanup.
- If explicit export coverage is still missing, add the smallest assertion set
  that will catch symbol drift.

## Definition of Done
- No private staging helper or alias introduced during phases 2 or 3 remains
  unless this phase intentionally keeps it as part of the final file shape.
- The public symbol set exposed from `git.py.__all__` is unchanged from the
  start of the migration.
- Any package-root re-export coverage needed to catch symbol drift is present.
- The final `git.py` layout and cleanup preserve caller-facing behavior under
  the focused git tests and the configured broad validation command.
- The configured broad validation command passes.

## Validation
- Run `uv run pytest tests/test_git.py`.
- If package-root export coverage is added or changed, run
  `uv run pytest tests/test_continuous_refactoring.py`.
- Finish with `uv run pytest`.
