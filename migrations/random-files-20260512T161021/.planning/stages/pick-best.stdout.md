**Choice:** `error-boundary-hardening`

**Why this is the best balance**
1. Lowest meaningful risk for a shipped surface: it improves internals at module boundaries without pushing on CLI/XDG/manifest contracts.
2. Highest clarity per unit change: the scope is explicit (`git.py`, `phases.py`, `planning_publish.py` + focused tests), and the success condition is concrete (`__cause__` preserved, consistent boundary translation).
3. Strong incremental verifiability: each phase has crisp, testable checkpoints and can be validated with existing failure-path assertions plus full `uv run pytest`.
4. Best taste fit: boundary wrapping discipline, low-comment readability, small abstractions only where they reduce repetition, and compatibility-first behavior.

**Runners-up (short)**
1. `test-fixture-consolidation-with-minimal-runtime-touch`: very safe and clean, but risks ending mostly test-structure work with weaker runtime signal improvement.
2. `migration-tick-planning-flow-first`: valuable when tick/planning behavior is actively unstable, but materially higher coordination risk and verification complexity for this migration’s “random files” scope.
