# Phase 3 — Release Pipeline Consistency Check

required_effort: low
effort_reason: Constrained consistency audit with change-only-if-mismatch policy.

## Scope
- `.github/workflows/release.yml`
- `tests/test_cli_version.py`
- `src/continuous_refactoring/__main__.py`

## Objectives
- Confirm release smoke commands in the release workflow match the locked module-entry/version contract.
- Apply the smallest possible workflow correction only when a concrete mismatch exists.

## Precondition
- Phase 2 is complete.
- `.github/workflows/release.yml` exists at the expected path.
- `tests/test_cli_version.py` and `src/continuous_refactoring/__main__.py` still represent the Phase 1 locked contract surface.
- No unresolved human-review hold is blocking release workflow edits.

## Implementation Instructions
1. Compare release workflow smoke invocation/assertion lines to Phase 1 contract behavior in `tests/test_cli_version.py` and module entry behavior in `src/continuous_refactoring/__main__.py`.
2. If aligned, make no workflow change.
3. If mismatched, edit only the specific smoke command/assertion lines in `.github/workflows/release.yml` needed to restore alignment.
4. Do not perform unrelated CI/workflow cleanup.

## Validation Steps
1. Re-read changed workflow lines to confirm they map directly to contract behavior under test.
2. Run the configured full validation command.

## Definition of Done
- Release workflow smoke behavior is confirmed aligned with Phase 1 locked module-entry/version contract.
- Any workflow edit is limited to directly mismatched smoke command/assertion lines in `.github/workflows/release.yml`.
- No files outside Scope were changed.
- Configured full validation command passes.
