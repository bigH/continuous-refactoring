# Repository State Context Utilities

## Strategy

Strengthen module coherence by adding a short-lived repo state abstraction in `git.py` and consuming it in `loop.py` and `phases.py`.

- Introduce immutable `RepositoryState` with head SHA and dirty flag.
- Add `capture_repository_state(repo_root: Path)` and `restore_repository_state(repo_root, state)`.
- Add `with temporary_git_state(repo_root)` context manager in `git.py` for guarded mutation.
- Replace duplicated `head_before`/`revert_to` usage in:
  - `loop.py` (`run_loop`, `run_once`, `_finalize_commit`)
  - `phases.py` (`execute_phase`)
  - `routing_pipeline.py` and `migration_tick.py` callsites where state reversion is conceptually tied to an attempt.

## Tradeoffs

Pros:
- Encapsulates a repeated rollback concern in one readable place.
- Makes branch-preserving retry behavior explicit and easier to test.
- Reduces accidental divergence between migration and normal run flows.

Cons:
- Touches multiple cluster files (`loop.py`, `phases.py`, `routing_pipeline.py`, `migration_tick.py`) in the same migration.
- Adds a context helper that can be overused if callers bypass it.
- More assertions needed around nested rollback paths and error handling.

## Estimated Phases

1. Baseline tests and scope framing.
- Add `tests/test_git.py` coverage for snapshot capture and restore behavior.
- Add regression tests in `tests/test_loop_migration_tick.py`, `tests/test_run.py`, and `tests/test_run_once.py` for retry rollback invariants.

2. Add state primitives in `src/continuous_refactoring/git.py`.
- New dataclass + `capture`, `restore`, and context manager APIs.
- Keep existing high-level operations calling these helpers rather than raw `git` commands.

3. Migrate callers in run orchestration.
- Replace manual `head_before` branches in `loop.py` and `phases.py` with context-managed sections.
- Keep any user-facing behavior unchanged in `routing_pipeline.py` and migration orchestration.

4. Validation.
- Run focused phase-targeted tests first.
- Run `uv run pytest` and inspect rollback-sensitive failures.

## Risk Profile

Medium risk. This is behavior-adjacent and spans active control-flow modules.

Mitigations:
- Use pure additive APIs first, then migrate one callsite per phase.
- Preserve existing return/raise behavior at each stage.
- Explicitly document why each callsite remains outside the context manager when restore logic would hide actionable partial outcomes.

## Best Fit

Best when the migration is allowed to touch orchestration modules and you want to reduce repeated state-management bugs rather than only tighten command boundaries.
