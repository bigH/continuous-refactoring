# Phase 1: Sync Live Migration and Characterize Attempt Behavior

## Objective

Make repo guidance truthful for this live `loop.py` migration, then lock down the retryable refactor attempt contracts before moving code out of `loop.py`.

Use `run_loop()` integration tests with real git repositories where possible. The point is to prove visible behavior: commits, rollback, artifacts, summaries, and retry transitions.

## Precondition

The migration has not moved `_run_refactor_attempt()` or `_retry_context()` yet. Ordinary refactor attempts are still executed by `continuous_refactoring.loop._run_refactor_attempt`, `run_loop()` still imports `maybe_run_agent` and `run_tests` directly from `continuous_refactoring.agent`, and the existing focused loop tests pass.

`AGENTS.md` may still say no active `loop.py` migration exists; that drift is the first thing this phase fixes before adding behavior coverage.

## Scope

Allowed files:

- `AGENTS.md`
- `tests/test_run.py`
- `tests/test_e2e.py`

Optional only if a shared helper becomes clearly misleading:

- `tests/conftest.py`

Do not refactor production code in this phase unless a new characterization test exposes a real existing bug. If that happens, keep the production fix tiny and call it out in the phase result.

## Instructions

1. Update `AGENTS.md` before touching tests.
   - Replace the stale "No active `loop.py` migration is present" statement with this migration name and a short note that it scopes extraction of ordinary retryable refactor attempts.
   - Clarify the package uniqueness rule: `__init__._SUBMODULES` is both the duplicate-symbol check input and root re-export list. Internal modules may define module-local `__all__` without being included in `_SUBMODULES`; adding a module to `_SUBMODULES` deliberately promotes its `__all__` symbols to root API.
   - Keep the guidance tight. Do not add broad migration prose.
2. Audit existing attempt tests in `tests/test_run.py` and list which of these contracts are already covered:
   - successful refactor creates exactly one driver commit
   - agent-created commits are squashed into the driver commit
   - validation failure rolls back workspace changes and commits
   - agent nonzero exit skips validation
   - retry prompts use sanitized failure context
   - `max_attempts=0` means unlimited until success
3. Add missing tests for agent-requested status transitions:
   - Codex writes `agent-last-message.md` with `decision: retry`, then a later retry succeeds.
   - Codex writes `decision: abandon` or `decision: blocked` after validation passes.
   - The workspace is rolled back for those requested transitions.
   - Persisted summary/events show the expected `decision`, `retry_recommendation`, `call_role`, and `failure_kind`.
4. Add or tighten a test for validation infrastructure failure:
   - `run_tests` raises `ContinuousRefactorError` for a per-attempt validation call.
   - The attempt returns retry behavior with `failure_kind == "validation-infra-failure"`.
   - Raw absolute repo paths and large command text are not fed back into the retry prompt.
5. Add or tighten a test for retry-start cleanup:
   - Leave untracked files and/or committed bad changes from retry 1.
   - Prove retry 2 starts from the original `HEAD` and a clean worktree.
   - This must indirectly protect the call to `discard_workspace_changes(repo_root)` at attempt start.
6. Add artifact path assertions around at least one retrying case:
   - first attempt logs under `attempt-001/refactor/`
   - retry logs under `attempt-001/retry-02/refactor/`
   - file names remain `agent.stdout.log`, `agent.stderr.log`, `tests.stdout.log`, `tests.stderr.log`, and Codex `agent-last-message.md`.
7. Keep tests outcome-oriented. Monkeypatch only real boundaries (`maybe_run_agent`, `run_tests`) and assert git/artifact/summary results instead of internal helper calls.

## Definition of Done

- `AGENTS.md` no longer claims there is no active `loop.py` migration.
- `AGENTS.md` explicitly distinguishes root re-export membership in `_SUBMODULES` from module-local `__all__`.
- Attempt behavior tests cover agent nonzero, validation failure, validation infrastructure failure, agent-requested retry/abandon/blocked, retry-start cleanup, artifact paths, successful commit, and agent-created commit squashing.
- New tests do not require the future `refactor_attempt.py` module.
- Existing monkeypatch paths remain valid.
- No production control-flow extraction has started.
- The repository is shippable after this phase.

## Validation

Run:

```sh
uv run pytest tests/test_run.py tests/test_e2e.py
```

If `tests/conftest.py` changes, also run:

```sh
uv run pytest tests/test_run_once.py tests/test_scope_loop_integration.py
```
