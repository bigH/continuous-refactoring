# Routing Parser Hardening

## Strategy
Treat `routing.py` as the primary target: make classification parsing and failure-reporting more robust to noisy model output, while keeping external behavior unchanged.

## Why this path
- Directly targets likely fragility area from random-file selection.
- High value/low dependency: mostly isolated module + focused tests.
- Supports taste principle of boundary translation while preserving internal signal.

## Estimated phases
1. **Phase: Characterize current behavior**
- Scope: `tests/test_routing.py`
- Work: add/adjust examples for malformed, trailing, case/whitespace-heavy classifier outputs; keep outcome-based assertions.
- `required_effort`: `low`

2. **Phase: Refactor parse and failure paths**
- Scope: `src/continuous_refactoring/routing.py`
- Work: simplify `_parse_decision` and failure logging flow with small helpers; preserve status/event payload contract.
- `required_effort`: `medium`

3. **Phase: Cross-check CLI version smoke relevance**
- Scope: `tests/test_cli_version.py`, `src/continuous_refactoring/__main__.py`
- Work: only touch if parser hardening exposes coupling assumptions in entrypoint tests.
- `required_effort`: `low`

## Tradeoffs
- Pros: meaningful resilience gains with contained scope.
- Cons: smaller user-visible payoff than broader CLI/workflow cleanup.

## Risk profile
- Overall risk: **Low to Medium**.
- Main risk: subtle event-log payload regressions (`call_finished` fields/order/summary wording expectations).
- Mitigation: preserve existing assertions; add targeted regression tests before refactor.
