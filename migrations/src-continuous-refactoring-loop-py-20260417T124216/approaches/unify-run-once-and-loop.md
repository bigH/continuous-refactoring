# Approach: Collapse `run_once` Into the Loop Core

## Summary

`run_once` (L1284–1420) and the per-target block inside `run_loop`
(L1497–1639) do nearly the same thing: clean worktree, prepare branch,
route, refactor, validate, commit. `run_once` duplicates a simplified
refactor+validate path instead of calling `_run_refactor_attempt`.
Unify them around a single `execute_target` function; make `run_once` a
1-target, 1-retry call through the same path.

## Target Shape

- New `execute_target(target, *, context) -> TargetOutcome` that contains:
  route → refactor-loop → persist-decision. Called once from `run_once`
  (max_attempts=1, no sleep) and per target from `run_loop`.
- A small `LoopContext` frozen dataclass carrying `repo_root, artifacts,
  taste, agent, model, effort, timeout, validation_command,
  commit_message_prefix, branch_name, push_remote, no_push, show_*`.
  (Single call site today, but two after unification — justifies the type.)
- `run_once` becomes ~40 lines: resolve target, build context, call
  `execute_target`, print diff-stat, return.
- `run_loop` loses its inline refactor-attempt loop; keeps
  baseline check, shuffle/limit, consecutive-failure accounting, sleep.

## Phases

1. **Introduce `LoopContext` + `execute_target`** extracted from
   `run_loop`'s inner block. `run_loop` calls it; `run_once` unchanged.
   Validation: full test suite + live run-once smoke.
2. **Rewrite `run_once`** to use `execute_target`. Delete the duplicated
   refactor/validate/commit block. Validation: existing `run_once` tests
   (see `tests/test_e2e.py`, `tests/test_scope_loop_integration.py`).
3. **Aggressive delete** of now-unused helpers specific to the old
   `run_once` path, if any surface.

## Tradeoffs

- **Pro**: Kills real duplication. Bugs fixed in one path (e.g.,
  agent-status handling, revert-on-failure) apply to both. Matches
  taste's "avoid needless duplication."
- **Pro**: `LoopContext` passes the smell test — more than one call
  site, real shape, not speculative.
- **Con**: `run_once`'s current shape is intentionally simpler (no retry
  loop, no consecutive-failure counter). Unifying forces `execute_target`
  to accept `max_retries=1`, which leaks loop semantics into one-shot.
  Keep the parameter explicit; don't hide it behind a mode flag.
- **Con**: Smaller payoff than a full split — `loop.py` still ~1300 lines.
  Best combined with split-by-domain, not as a substitute.

## Risk Profile

Low. Behavioral equivalence is testable: `run_once` must produce the
same commit + branch + artifacts shape before and after. Property:
`run_loop` with `max_refactors=1, max_attempts=1` on the same target
should produce the same commit SHA kind as `run_once`.
