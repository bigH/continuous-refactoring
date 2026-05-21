# Phase 3: PR Title Policy Adjustment (Review-Gated)

required_effort: high
effort_reason: PR title policy changes are user-facing workflow contract changes and require careful compatibility framing and explicit review communication.

## Scope
- `.github/workflows/pr-title.yml`
- Any directly related tests/fixtures/docs that define accepted PR title patterns
- Migration notes/review prompt content that explains interface impact

## Goals
- Apply a deliberate PR title policy behavior adjustment only if needed.
- Make user-facing impact explicit, concrete, and review-friendly.

## Precondition
- Phase 1 and Phase 2 are complete.
- There is a concrete, documented reason for policy change (not cleanup-only churn).
- The current accepted/rejected title behavior is captured by tests so change impact is measurable.

## Implementation Instructions
1. Change PR-title matching behavior only for the explicitly intended cases.
2. Update/add tests to show before/after expectations for affected title examples.
3. Update any user-facing examples/messages so accepted syntax is unambiguous.
4. In review-facing notes, explicitly name the interface behavior change (what titles now pass/fail) and why.

## Validation Steps
- Run PR-title focused checks:
  - `uv run pytest -k "pr title or pr_title or workflow"`
- Run full validation command:
  - `uv run pytest`

## Definition of Done
- PR title policy change is intentional, narrowly scoped, and fully covered by deterministic tests.
- Review notes explicitly describe the interface behavior change and expected user impact.
- Full configured validation command passes.
- Repository remains shippable with workflow behavior updated in a clearly documented, review-gated way.
