Chosen approach: **`interface-first-boundary-hardening`**

Why this wins:
- Best risk/clarity balance for a shipped system: it locks boundary behavior first, then refactors behind tests.
- Strongest match to taste: boundary-level error translation, compatibility-first changes, and explicit protection of CLI/XDG/migration contracts.
- Most incrementally verifiable path: each phase has clear pass/fail signals, and Phase 2 is safely revertible while keeping Phase 1 guardrails.

Why not the others:
- `eligibility-engine-simplification`: higher regression risk too early in scheduler-critical logic.
- `minimal-safe-cleanup`: safest, but likely under-delivers on meaningful structural improvement.
- `planning-transaction-integrity-first`: solid, but indirect for this target; over-anchors on planning publish before the immediate eligibility/boundary cleanup.

Recommended phase posture (keeping lowest safe effort):
1. Phase 1 (contract tests): `low`
2. Phase 2 (boundary/helper refactor): `medium`
3. Phase 3 (prompt/test consistency check): `low`
