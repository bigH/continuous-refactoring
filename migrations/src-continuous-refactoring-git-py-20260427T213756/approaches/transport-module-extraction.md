# Transport Layer Extraction for Git Commands

## Strategy

Extract subprocess execution into a dedicated transport module and keep `git.py` as domain behavior.

- Add `src/continuous_refactoring/git_transport.py` with only one job: run command tuples, normalize output, and raise typed command-level exceptions.
- Keep `src/continuous_refactoring/git.py` focused on repository semantics (commit, branch, status, reset).
- Preserve compatibility by keeping `run_command` as a thin wrapper in `git.py` that delegates to the transport layer.
- Update package exports in `src/continuous_refactoring/__init__.py` only if transport symbols become intentionally public.
- Add docs/tests updates where module boundary behavior is validated.

## Tradeoffs

Pros:
- Stronger domain boundaries, easier future transport swaps (e.g., dry-run/testing transport).
- Cleaner test seam for command transport vs git behavior.
- Prepares for multi-command tracing without leaking transport details to every caller.

Cons:
- Adds a new module plus import rewiring; higher churn for a small immediate gain.
- Requires migration through multiple files in the cluster for consistency:
  - `git.py`, `loop.py`, `phases.py`, `routing_pipeline.py`, `migration_tick.py`, `__init__.py`
- Higher chance of import-cycle mistakes with the strict package uniqueness check.

## Estimated Phases

1. Introduce transport module.
- Add transport API and tests for command execution contract in `tests/test_git.py`.
- Keep API tiny and private initially.

2. Rewire `git.py`.
- Replace direct `subprocess.run` with transport call paths.
- Ensure existing public helpers keep their current names and behavior.

3. Audit cluster callsites.
- Update tests that monkeypatch `continuous_refactoring.git.run_command` to keep spies stable.
- Confirm no import shadowing in `loop.py`, `phases.py`, and `routing_pipeline.py` after split.

4. Final verification.
- Run full `uv run pytest` and adjust for any export ordering issues.

## Risk Profile

Medium-to-high. Biggest risk is boundary churn in a module with broad import surface.

Mitigations:
- Keep the transport module private by default.
- Avoid API expansion beyond command execution in phase 1.
- Validate exports with `continuous_refactoring.__init__` path immediately after each phase.

## Best Fit

Best when you want long-term structural growth and plan to reuse this command layer beyond this migration.
