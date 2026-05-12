# Approach: Error Boundary Hardening

## Strategy
Tighten exception translation at module boundaries only, then unify failure-path assertions across `tests/test_git.py`, `tests/test_phases.py`, and `tests/test_planning_publish.py`. Focus on preserving `__cause__` while improving error signal consistency.

## Why this approach
- Highest reliability gain with limited behavior risk.
- Aligns directly with taste: boundary translation, low-comment, clarity-first code shape.
- Keeps CLI/state contracts intact while improving internals.

## Tradeoffs
- Pros: clearer failure diagnostics, less flaky failure assertions, safer refactor surface.
- Cons: limited structural cleanup; some duplication may remain in test fixtures.

## Estimated phases

### Phase 1: Map current exception boundaries
- Scope: `git.py`, `phases.py`, `planning_publish.py` and touched test expectations.
- Deliverable: inventory of wrap points, duplicated error text, and cause-chain guarantees.
- required_effort: `low`
- Risk: low

### Phase 2: Normalize boundary wrapping and messages
- Scope: source modules only; no contract changes to CLI flags or manifest schema.
- Deliverable: consistent boundary errors with nested causes preserved and no intra-module over-wrapping.
- required_effort: `medium`
- Risk: medium

### Phase 3: Update and tighten tests for error payloads
- Scope: `tests/test_git.py`, focused sections of `tests/test_phases.py` and `tests/test_planning_publish.py`.
- Deliverable: outcome-focused assertions for message fragments + `__cause__` shape.
- required_effort: `low`
- Risk: low

### Phase 4: Full regression run and targeted cleanup
- Scope: remove obsolete fixture helpers/legacy branches found during edits.
- Deliverable: green `uv run pytest` and smaller failure-path surface.
- required_effort: `low`
- Risk: low

## Risk profile
Overall risk: **Low to Medium**.
Primary risk is changing user-visible wording in exceptions that tests (or callers) treat as contract. Mitigation: preserve semantic message anchors already asserted in tests and avoid CLI text changes unless explicitly reviewed.
