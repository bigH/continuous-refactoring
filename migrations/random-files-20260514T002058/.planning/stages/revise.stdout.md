Updated the migration plan artifacts in the staged work dir:

- `plan.md`
- `phase-2-boundary-focused-routing-cleanup.md`
- `phase-3-release-pipeline-consistency-check.md`

What changed to address review findings:
1. Phase 2 precondition is now objective and start-gateable (specific files/surfaces must still exist), with no “intent” language.
2. Phase 2 Definition of Done now has concrete acceptance criteria for duplication removal and preserved observable outcomes.
3. Phase 3 scope is now explicitly bounded to a file allowlist:
   - `.github/workflows/release.yml`
   - `tests/test_cli_version.py`
   - `src/continuous_refactoring/__main__.py`

Phase 1 remained valid and unchanged.
