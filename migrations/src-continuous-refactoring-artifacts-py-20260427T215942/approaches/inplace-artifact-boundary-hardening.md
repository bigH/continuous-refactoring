# In-place artifact boundary hardening

## Strategy

Keep module boundaries intact and make failure contracts explicit where side effects cross module seams.

1. Baseline current behavior with regression tests that assert boundary failures carry `__cause__` where this migration intends to improve context.
2. Tighten `artifacts.py` with private boundary helpers for event writes, summary serialization, and atomic persistence, then apply them to existing callsites with no public API change.
3. Extend callsite-level wrappers in `agent.py`, `git.py`, `phases.py`, and `migration_tick.py` so boundary failures bubble with preserved causes while preserving current control flow.
4. Update orchestration and CLI surfaces in `loop.py`, `config.py`, and `cli.py` to keep recovery/abort semantics unchanged while preserving richer causal context.
5. Close with a migration-wide contract lock, duplicate-symbol safety checks, and full-suite verification.

## Tradeoffs

Pros:
- No module splitting or symbol churn.
- Localized change surface anchored to observed co-change boundaries.
- Minimal stack distortion because boundaries stay aligned with existing module seams.

Cons:
- Additional wrapper indirection in hot paths can lengthen tracebacks.
- Requires coordinated test updates across adjacent modules before the final lock step.

## Compatibility stance

No canary/cutover rollout in this repo. The migration is a straight in-place refinement with stronger boundary contracts and stable behavior defaults.

## Phase intent

- `phase-1` records a stable baseline and ensures the suite will catch causal-regression mistakes.
- `phase-2` introduces the module-level helpers in `artifacts.py` and validates their persistence contract.
- `phase-3` applies adjacent boundary wrappers at seams, including migration-tick reporting.
- `phase-4` propagates the contract safely through loop/CLI/config orchestration points.
- `phase-5` freezes contracts and runs full validation for shipping confidence.
