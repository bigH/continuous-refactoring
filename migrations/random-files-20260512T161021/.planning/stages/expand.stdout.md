Created the planning artifacts in the staged migration workspace:

- `plan.md`
- `phase-1-map-exception-boundaries.md`
- `phase-2-normalize-boundary-wrapping.md`
- `phase-3-tighten-error-path-tests.md`
- `phase-4-regression-and-dead-path-cleanup.md`

Highlights:
- 4 ordered, independently verifiable phases with explicit dependencies and Mermaid dependency graph.
- Clear separation between `## Precondition` and `## Definition of Done` in every phase.
- Baseline contract respected: no preconditions restate “tests green” invariants.
- `required_effort` included only where needed (Phase 2: `medium`, with reason).
- Every phase requires targeted validation plus full `uv run pytest` before completion.
