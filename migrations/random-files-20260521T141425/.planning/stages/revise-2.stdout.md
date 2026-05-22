Updated the migration planning artifacts in the staged work dir with the requested refinements:

- [plan.md](/Users/hiren/.local/share/continuous-refactoring/projects/dfdec7e7-73c4-45c3-9786-693784acfd83/planning/random-files-20260521T141425/20260522T161153-731704-48db80aa86304b11a578594fd35fc409/work/random-files-20260521T141425/plan.md)
- [phase-1-contract-regression-net.md](/Users/hiren/.local/share/continuous-refactoring/projects/dfdec7e7-73c4-45c3-9786-693784acfd83/planning/random-files-20260521T141425/20260522T161153-731704-48db80aa86304b11a578594fd35fc409/work/random-files-20260521T141425/phase-1-contract-regression-net.md)
- [phase-2-internal-cleanup-behind-contracts.md](/Users/hiren/.local/share/continuous-refactoring/projects/dfdec7e7-73c4-45c3-9786-693784acfd83/planning/random-files-20260521T141425/20260522T161153-731704-48db80aa86304b11a578594fd35fc409/work/random-files-20260521T141425/phase-2-internal-cleanup-behind-contracts.md)
- [phase-3-interface-shift-review-gate.md](/Users/hiren/.local/share/continuous-refactoring/projects/dfdec7e7-73c4-45c3-9786-693784acfd83/planning/random-files-20260521T141425/20260522T161153-731704-48db80aa86304b11a578594fd35fc409/work/random-files-20260521T141425/phase-3-interface-shift-review-gate.md)

What changed per your feedback:
- Removed `phase-1-contract-inventory.md` from Phase 1 preconditions and kept it in Phase 1 Definition of Done.
- Tightened Phase 1 scope to explicitly bound it to behavior tests plus the single inventory artifact, with minimal production edits only when strictly needed for test observability.
- Raised Phase 3 `required_effort` to `high` and added a concrete `effort_reason` tied to release-facing interface-risk and gating correctness.
