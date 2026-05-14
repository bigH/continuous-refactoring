Updated the migration planning artifacts in the staged work dir to address all review findings:

- Tightened Phase 3 scope to an explicit file allowlist and added a hard “no changes outside allowlist” DoD check.
- Added `required_effort: low` + concrete `effort_reason` to Phase 3.
- Made Phase 1 DoD concretely verifiable by requiring explicit assertions across the three contract surfaces (visibility filtering, eligibility/ordering, error surfacing) with observable outcomes.
- Upgraded Phase 2 `effort_reason` to operational detail tied to concrete risk points: ordering-sensitive candidate enumeration and deferred-manifest write timing.
- Kept plan ordering/dependencies/validation strategy intact since those were already accepted.

Files updated:
- `/Users/hiren/.local/share/continuous-refactoring/projects/dfdec7e7-73c4-45c3-9786-693784acfd83/planning/random-files-20260514T002712/20260514T001935-704380-1809365971c346d495e115c15c0369a8/work/random-files-20260514T002712/phase-1-boundary-contract-tests.md`
- `/Users/hiren/.local/share/continuous-refactoring/projects/dfdec7e7-73c4-45c3-9786-693784acfd83/planning/random-files-20260514T002712/20260514T001935-704380-1809365971c346d495e115c15c0369a8/work/random-files-20260514T002712/phase-2-boundary-helper-refactor.md`
- `/Users/hiren/.local/share/continuous-refactoring/projects/dfdec7e7-73c4-45c3-9786-693784acfd83/planning/random-files-20260514T002712/20260514T001935-704380-1809365971c346d495e115c15c0369a8/work/random-files-20260514T002712/phase-3-prompt-test-consistency-reconciliation.md`
