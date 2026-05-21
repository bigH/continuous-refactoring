# Phase 2: Internal Cleanup Behind Contracts

## Goal
Simplify random-targeted internals and delete dead/redundant paths while preserving Phase 1 locked behavior.

## Scope
- Only random-targeted source files selected for this migration.
- Internal readability improvements, dead-path deletion, and control-flow simplification.
- No intentional change to released interfaces (CLI behavior, repo-written files, XDG/project state, migration manifest structure, or other install-visible contracts).

## Precondition
- Phase 1 is complete.
- `phase-1-contract-inventory.md` exists and Phase 1 regression coverage is present in the repository.
- Candidate source edits remain inside the random-targeted migration scope.

## Implementation Instructions
1. Remove dead branches/helpers/fallback paths made unnecessary by current behavior contracts.
2. Keep boundary error translation with exception nesting only at module boundaries.
3. Use small readability-first abstractions only when they reduce repetition or branch complexity.
4. If an interface behavior must change, isolate and document that delta for Phase 3 instead of blending it into broad cleanup.

## Validation Steps
1. Run targeted tests that cover cleaned paths, including all Phase 1 contract tests.
2. Confirm each deleted helper/symbol still has its externally observable behavior protected by surviving behavior-level test paths.
3. Run the configured full validation command.

## Definition of Done
- Scoped internal dead/redundant paths are removed or simplified without regressing locked behavior.
- Surviving behavior-level tests cover externally observable effects previously provided by removed helpers/symbols.
- Any intentional interface delta is explicitly documented and handed off to Phase 3.
- The full configured validation command passes.

required_effort: medium
effort_reason: Internal deletions across heterogeneous random files need careful contract-preserving reasoning.
