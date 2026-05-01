# Reconstructed Planning Step: expand

Expanded `inplace-domain-seams` into the published migration plan and phase docs.

Published files:
- `plan.md`
- `phase-1-lock-git-behavior.md`
- `phase-2-reorganize-domain-flow.md`
- `phase-3-tighten-error-boundaries.md`
- `phase-4-trim-helper-shapes-and-verify-surface.md`

The resulting plan keeps all phases behind behavior locks and requires broad
validation with `uv run pytest` before any phase is considered complete.

