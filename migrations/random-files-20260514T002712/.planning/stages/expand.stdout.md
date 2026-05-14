Created all required planning artifacts in the staged migration workspace:

- `plan.md`
- `phase-1-boundary-contract-tests.md`
- `phase-2-boundary-helper-refactor.md`
- `phase-3-prompt-test-consistency-reconciliation.md`

What’s included:
- Numbered, dependency-ordered phases with a Mermaid dependency graph in `plan.md`.
- Per-phase scope, out-of-scope, phase-local `## Precondition`, `## Definition of Done`, and validation steps.
- `required_effort`/`effort_reason` included only where needed (Phase 2, `medium`), with lowest safe effort elsewhere.
- Baseline contract respected: preconditions do not restate “tests green” invariants; DoD still requires full validation pass.
