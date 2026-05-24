# Phase 2: Internal Cleanup Behind Contracts

## Goal
Simplify random-targeted internals and remove dead/redundant paths while preserving Phase 1 locked behavior.

## Scope
- Only random-targeted source files selected for this migration.
- Source cleanup scope is anchored to `src/continuous_refactoring/__main__.py`.
- `tests/test_main_entrypoint.py` and `LICENSE` are contract-validation surfaces, not internal cleanup targets.
- Internal readability improvements, dead-path deletion, and control-flow simplification.
- No intentional change to released interfaces (CLI behavior, repo-written files, XDG/project state, migration manifest structure, or other install-visible contracts).

## Precondition
- Phase 1 is complete.
- `phase-1-contract-inventory.md` and its Phase 1 regression coverage are present.
- Candidate edits remain inside the anchored migration scope defined in Phase 1.

## Implementation Instructions
1. Remove dead branches/helpers/fallback paths that are unnecessary under current contracts.
2. Translate/wrap errors only at module boundaries; preserve signal when bubbling within a module.
3. Introduce small abstractions only when they reduce repetition or branch complexity.
4. If an interface behavior change is required, isolate and document that delta for Phase 3 instead of blending it into broad cleanup.

## Validation Steps
1. Run targeted tests covering cleaned paths, including all Phase 1 contract tests.
2. Confirm surviving behavior-level tests still cover externally observable effects previously provided by removed helpers/symbols.
3. Run the configured full validation command.

## Definition of Done
- Scoped internal dead/redundant paths are removed or simplified without regressing locked behavior.
- Surviving behavior-level tests cover externally observable effects previously provided by removed helpers/symbols.
- Any intentional interface delta is explicitly documented for Phase 3.
- The full configured validation command passes.

required_effort: medium
effort_reason: Cross-file internal cleanup with contract-preserving constraints needs careful sequencing.
