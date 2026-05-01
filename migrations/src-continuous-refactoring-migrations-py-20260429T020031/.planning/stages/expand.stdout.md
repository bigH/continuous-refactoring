# Reconstructed Planning Step: expand

Expanded `manifest-ops-module-split` into the published migration plan and phase
docs.

Published files:
- `plan.md`
- `phase-1-lock-current-surface.md`
- `phase-2-extract-manifest-ops.md`
- `phase-3-redirect-internal-callers.md`
- `phase-4-tighten-boundary-contracts.md`

The resulting plan keeps `migrations.py` as the stable public facade while
moving implementation detail into a focused internal operations module.

