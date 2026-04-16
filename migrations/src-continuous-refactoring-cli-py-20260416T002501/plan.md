# Migration plan: error-boundary-convergence

## Migration metadata
- ID: `src-continuous-refactoring-cli-py-20260416T002501`
- Scope label: `local-cluster`
- Chosen approach: `approaches/error-boundary-convergence.md`
- Primary target file: `src/continuous-refactoring/cli.py`

## In-scope files
- `src/continuous_refactoring/cli.py`
- `src/continuous_refactoring/loop.py`
- `src/continuous_refactoring/config.py`
- `src/continuous_refactoring/artifacts.py`
- `src/continuous_refactoring/__main__.py`
- `src/continuous_refactoring/__init__.py`
- `src/continuous_refactoring/prompts.py`
- `src/continuous_refactoring/agent.py`

## Why this order is safe
This is a boundary migration in one cluster. We first define a stable domain error contract, then reshape loop internals to emit it, then make CLI the single exit translation boundary, then move path/project resolution into config so CLI remains purely orchestration + presentation.

Each phase below includes checks that are executable and mechanically verifiable so a phase cannot be marked ready by prose-only assertions.

## Planned phase dependencies
1. [`phase-1-boundary-contract-and-exit-surface.md`](phase-1-boundary-contract-and-exit-surface.md)
   - No dependency
2. [`phase-2-loop-domain-error-shape.md`](phase-2-loop-domain-error-shape.md)
   - Depends on phase 1
3. [`phase-3-cli-boundary-translation.md`](phase-3-cli-boundary-translation.md)
   - Depends on phase 1 and phase 2
4. [`phase-4-config-path-boundary-alignment.md`](phase-4-config-path-boundary-alignment.md)
   - Depends on phase 2 and phase 3

## Global validation strategy
1. Phase-specific `ready_when` checks must pass before moving to the next phase.
2. Each phase keeps `python -m py_compile` passing for files it edits.
3. Import and symbol smoke check after each phase:
   ```bash
   python - <<'PY'
   import continuous_refactoring
   from continuous_refactoring import cli, loop, config, artifacts
   print("import ok", continuous_refactoring.__name__)
   print("artifact contract exports", hasattr(artifacts, "LoopExecutionError"))
   print("loop exports", hasattr(loop, "run_once"), hasattr(loop, "run_loop"))
   print("cli entry", callable(cli.cli_main))
   print("config loaded", callable(config.resolve_project))
   PY
   ```
4. Validation commands should be added to each phase file and executed at phase boundaries; target is partial correctness and unchanged CLI behavior within phase.

## Global behavior invariants
- CLI exit surface remains the process boundary.
- Exit classes remain:
  - `0` success
  - `1` runtime/domain issue
  - `2` usage/schema issue
  - `130` interrupt
- `run_once` and `run_loop` continue to return only `int` statuses (success/interrupt semantics preserved).
- `artifacts.finish(...)` remains idempotent-per-call and always runs once per loop invocation even on failures.
- Any new transitional names must be truthful and rollout-safe (e.g., `canary`, `upgraded`, `version_being_rolled_out`); avoid ambiguous temporary naming.
