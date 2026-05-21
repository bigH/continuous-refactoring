Chosen approach: **`behavior-first-random-file-stabilization`**

Why this is the best balance:

- **Risk:** lower than dead-path-first, because it stabilizes externally visible behavior before cleanup and explicitly adds a human-review gate if interface shifts appear.
- **Clarity:** the phase story is clean and reviewable: prove contracts, refactor behind them, escalate only if boundaries move.
- **Incremental verifiability:** each phase has a crisp verification target and natural rollback point; Phase 1 gives immediate confidence for later deletions.

Why not the others:

- `delete-dead-paths-then-reprove`: strong cleanup upside, but too much upfront blast radius for a random-file migration; higher chance of uncovering hidden coupling late.
- `minimal-entrypoint-and-license-guardrails`: safest, but likely under-shoots the migration’s refactoring value unless the random set is truly only boundary trivia.

Taste tie-break application:

- Taste asks for **aggressive dead-code deletion** in non-shipped internals, but also **compatibility-first handling** and **human review for released interfaces**.  
- This approach best reconciles both by sequencing: lock behavior first, then delete safely, then require explicit interface review if needed.
