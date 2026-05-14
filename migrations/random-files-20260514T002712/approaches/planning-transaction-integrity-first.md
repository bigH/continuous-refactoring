# Approach: Planning Transaction Integrity First

## Strategy
Treat planning/workspace publication semantics as the anchor, then align migration runtime behavior around those guarantees. Start with planning publish invariants (`tests/test_planning_publish.py`) and consistency gates, then simplify tick/manifest flow.

## Why this approach
- Good when transaction/publish correctness is the biggest operational risk.
- Makes staged-vs-live safety guarantees explicit before runtime cleanups.
- Strong fit for this codebase’s atomic publish/rollback design.

## Tradeoffs
- Indirect path to random-file target scope in `migration_tick.py`.
- May defer obvious cleanup in tick logic until publish constraints are fully pinned.
- Can feel test-heavy early.

## Estimated Phases

### Phase 1: Strengthen publish/consistency invariants
- Scope: `tests/test_planning_publish.py`, consistency-facing helpers indirectly referenced by migration tick behavior.
- Work: fill edge-case gaps around stale snapshots, rollback/failure paths, and blocking findings.
- required_effort: `medium`
- Risk: Medium.

### Phase 2: Align tick preflight/eligibility with invariants
- Scope: `src/continuous_refactoring/migration_tick.py`, `src/continuous_refactoring/migrations.py`.
- Work: reduce branch ambiguity in candidate enumeration and invalid-manifest preflight handling while preserving public behavior.
- required_effort: `medium`
- Risk: Medium.

### Phase 3: Prompt contract confirmation
- Scope: `tests/test_prompts.py`.
- Work: ensure planning prompt assertions still match intended staged-workflow and resume-input boundaries.
- required_effort: `low`
- Risk: Low.

## Risk Profile
- Overall risk: Medium.
- Primary failure mode: over-coupling runtime tick behavior to planning-publish assumptions.
- Mitigation: keep module boundaries explicit and avoid interface changes without review.

## Rollback posture
- Phase-2 changes are revertible if Phase-1 tests remain as invariant guardrails.
