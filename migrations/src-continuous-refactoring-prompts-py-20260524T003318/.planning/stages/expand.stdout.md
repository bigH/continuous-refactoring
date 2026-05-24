Created the migration planning artifacts in the staged workspace:

- `plan.md`
- `phase-1-contract-inventory.md`
- `phase-2-contract-consolidation.md`
- `phase-3-test-hardening.md`
- `phase-4-final-verification-and-review-note.md`

What’s included:
- Numbered phases with strict ordering and risk-reduction flow.
- Explicit dependency graph and per-phase dependencies in `plan.md`.
- Each phase has clear scope, `## Precondition`, `## Definition of Done`, and validation steps.
- `required_effort`/`effort_reason` only on phases that need it (Phases 2 and 3, both `medium`).
- Preconditions are phase-local and do not restate baseline-green invariants.
