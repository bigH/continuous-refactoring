**Choice: `interface-first-hardening`**

It has the best risk/clarity/verifiability balance for this repo right now.

- Lowest boundary risk: it explicitly protects CLI effort semantics, prompt contracts, and workflow behavior before internal cleanup.
- Best taste match: “safer compatibility paths for shipped systems” and “treat released package interfaces as human-review territory” are first-class in this approach.
- Incremental and testable: Phase 1 is low-effort, outcome-focused guardrails; Phase 2 refactors behind stable contracts; Phase 3 makes interface changes optional and review-gated.

**Why not the others (short):**
- `effort-engine-consolidation`: cleaner internals, but higher drift risk early; it optimizes maintainability before boundary safety.
- `test-first-boundary-pruning`: good hygiene, but contract-vs-incidental pruning can create reviewer ambiguity and accidental guard loss.

**Suggested tie-break framing:** choose safety-first contract locking when interfaces are active and shipped; optimize internals second.
