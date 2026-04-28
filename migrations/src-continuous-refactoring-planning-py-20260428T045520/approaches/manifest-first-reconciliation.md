# Manifest-First Reconciliation

## Strategy
Treat planning as a manifest-driven state transition workflow rather than a linear script with incidental manifest writes. Re-center `planning.py` around a few explicit state transitions:

- initialize planning manifest
- execute stage
- reconcile filesystem outputs back into manifest state
- finalize decision

In this shape, manifest refresh becomes a first-class concept instead of being embedded in `_touch_manifest()` calls scattered through `run_planning()`.

## Why It Fits The Taste
- Pushes toward truthful domain language: planning state, reconciliation, finalization.
- Improves boundary clarity between generated files and persisted migration state.
- Deletes incidental control-flow noise instead of wrapping it in thin helpers.

## Likely Changes
- Introduce explicit reconciliation helpers for approaches, plan text, and discovered phases.
- Replace generic `_touch_manifest()` updates with named state transitions.
- Potentially model planning stages with a small result object carrying stdout plus reconciliation needs.
- Strengthen tests around manifest lifecycle, especially status transitions and phase cursor repair when phase files change.

## Tradeoffs
- Pro: Best domain clarity if the module is expected to keep growing.
- Pro: Makes manifest behavior easier to reason about than timestamp-only touching.
- Pro: Creates a stronger base for future planning features.
- Con: Highest churn of the candidate set.
- Con: Easier to overshoot and redesign more than this migration needs.
- Con: More likely to expose awkward boundaries with `migrations.py` and prompt-stage handling.

## Estimated Phases
1. `medium` — Add tests that pin manifest lifecycle semantics, reconciliation behavior, and error paths.
2. `high` — Refactor planning flow around explicit state transitions and reconciliation helpers.
3. `medium` — Simplify remaining orchestration, remove obsolete helper paths, and re-verify the narrowed public surface.

## Risk Profile
- Delivery risk: medium-high
- Regression risk: medium-high
- Design payoff: high
- Best when: the migration wants a structural cleanup that can support more planning complexity later

## Failure Modes To Watch
- Smearing manifest responsibilities across `planning.py` and `migrations.py` instead of clarifying them.
- Rephrasing state without reducing actual complexity.
- Spending effort on architecture when the real issue is just repeated stage wiring.
