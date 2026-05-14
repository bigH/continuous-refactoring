Created the migration planning artifacts in the staged work dir:

- `plan.md`
- `phase-1-freeze-interface-contracts.md`
- `phase-2-boundary-focused-routing-cleanup.md`
- `phase-3-release-pipeline-consistency-check.md`

They include:
- Numbered phase order with explicit dependencies and Mermaid graph.
- Phase-local preconditions (no baseline-green restatements).
- Clear `## Definition of Done` per phase.
- Independent validation steps per phase, ending with configured full validation command.
- Effort annotations using the chosen profile: `low`, `medium`, `low` with short reasons.
