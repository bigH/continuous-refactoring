Updated the staged migration plan in the planning workspace.

What changed:
- Fixed the missing dependency story by acknowledging the real helper consumers: `migration_tick.py`, `review_cli.py`, and `migration_cli.py`.
- Split the old Phase 3 into two honest phases:
  - `phase-3-redirect-operational-callers.md`
  - `phase-4-redirect-readonly-callers.md`
- Moved boundary cleanup to `phase-5-tighten-boundary-contracts.md`.
- Rewrote `plan.md` so dependencies, blast radius, and validation sequencing line up with the actual import graph.

Artifacts now present in the staged migration dir:
- `plan.md`
- `phase-1-lock-current-surface.md`
- `phase-2-extract-manifest-ops.md`
- `phase-3-redirect-operational-callers.md`
- `phase-4-redirect-readonly-callers.md`
- `phase-5-tighten-boundary-contracts.md`

The old misleading `phase-3-redirect-internal-callers.md` and previous phase 4 file were removed.
