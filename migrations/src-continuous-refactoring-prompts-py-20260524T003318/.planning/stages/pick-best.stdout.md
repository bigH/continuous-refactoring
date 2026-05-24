**Chosen approach: `prompt-surface-hardening`**

Best balance is clear: it’s the lowest-risk path that still improves maintainability and verifiability in a load-bearing prompt module.

Why this wins:
1. **Risk control:** `prompts.py` is contract-sensitive (tests, parsing, CLI/operator expectations). This approach minimizes blast radius and keeps behavior stable.
2. **Incremental verifiability:** each phase has tight checkpoints (inventory → consolidate internals → harden invariants → full suite), so regressions show up early.
3. **Clarity without over-architecture:** it reduces repetition via small helpers/anchors, matching taste guidance to prefer small abstractions and avoid speculative restructuring.
4. **Interface safety:** it explicitly preserves exports and semantics unless intentionally changed and surfaced for review, aligned with your “human-review for released interfaces” rule.

Runner-ups (short):
- `composable-prompt-builders`: good design direction, but more churn and parity risk than needed for this migration.
- `split-prompts-by-domain`: strongest structural cleanup, but high churn/high coordination risk; wrong move unless we’re intentionally paying that cost now.
