# Release Smoke Alignment

## Strategy
Start from release workflow and align runtime smoke tests with CLI entry/version behavior, then tighten source/tests to make that contract explicit and durable.

## Why this path
- Anchors refactor to shipped artifact behavior (wheel + sdist invocation paths).
- Good fit when random selection includes both workflow and CLI/version tests.
- Surfaces interface-impacting changes early for human review.

## Estimated phases
1. **Phase: Define artifact-level contract**
- Scope: `.github/workflows/release.yml`, `tests/test_cli_version.py`
- Work: make sure the release smoke commands and unit tests assert the same contract for both binary entrypoint and `python -m`.
- `required_effort`: `low`

2. **Phase: Entry-point simplification**
- Scope: `src/continuous_refactoring/__main__.py`, possibly `src/continuous_refactoring/cli.py`
- Work: minimal cleanup to keep module boundary obvious and stable; no behavior changes without explicit review callout.
- `required_effort`: `low`

3. **Phase: Routing collateral cleanup (optional)**
- Scope: `src/continuous_refactoring/routing.py`, `tests/test_routing.py`
- Work: opportunistic local cleanup only if touched indirectly; defer structural ideas.
- `required_effort`: `medium`

## Tradeoffs
- Pros: strongest packaging/release confidence; catches real-install regressions.
- Cons: may under-deliver on deep code-quality improvements in routing internals.

## Risk profile
- Overall risk: **Medium** (workflow changes can be high-blast-radius despite small diffs).
- Main risk: overfitting tests/workflow to current implementation details.
- Mitigation: lock onto user-facing behavior (`--version` and module execution), not internal call structure.
