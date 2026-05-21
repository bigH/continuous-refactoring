# Phase 2: Internal Cleanup Behind Contracts

## Goal
Refactor random-targeted internals and delete dead/duplicative paths while preserving behavior proven by Phase 1.

## Scope
- Only random-targeted source files selected for this migration.
- Internal simplification, dead-path deletion, and readability improvements.
- No intentional changes to released interfaces (CLI behavior, XDG/project state layout, repo-written artifact contracts, migration manifest shape, or other system interaction contracts).

## Precondition
- Phase 1 is complete and its regression tests are present.
- The source files planned for cleanup remain within the random-targeted migration scope.
- Any helper/symbol slated for deletion has at least one surviving behavior-level test path covering its externally observable effects.

## Implementation Instructions
1. Remove dead branches/helpers and redundant fallback code now covered by the Phase 1 regression net.
2. Keep module-boundary error translation with nested exceptions; do not introduce intra-module translation churn that hides signal.
3. Prefer small, readability-first abstractions and straightforward control flow; avoid speculative interfaces for single implementations.
4. If cleanup reveals a required interface behavior change, stop interface mutation work and route that delta to Phase 3.

## Validation Steps
1. Run targeted tests covering the cleaned paths, including Phase 1 regression tests.
2. Run the configured full validation command.
3. Verify no unintended interface behavior delta remains undocumented.

## Definition of Done
- Dead/duplicative internal paths in scoped random-targeted files are removed or simplified without regressing locked behavior.
- Externally visible behavior covered in Phase 1 remains unchanged.
- Any discovered intentional interface change is isolated and explicitly deferred to Phase 3 review gating.
- The full configured validation command passes.

required_effort: medium
effort_reason: Safe deletion/refactor across heterogeneous random files requires careful reasoning against contract tests.
