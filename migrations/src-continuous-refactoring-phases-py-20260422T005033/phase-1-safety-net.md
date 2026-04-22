# Phase 1: Safety Net

## Objective

Lock down the important `execute_phase()` contracts before reshaping the function.

The current tests cover happy path, final phase completion, validation failure, retry success, retry exhaustion, and sanitized retry context. This phase fills the missing failure and manifest-completion edges so later extraction can be mechanical.

## Precondition

The migration has not modified `execute_phase()` yet. `continuous_refactoring.phases.execute_phase` still contains the current in-place control flow, public imports and monkeypatch targets are unchanged, and the existing `tests/test_phases.py` suite passes.

## Scope

Allowed files:

- `tests/test_phases.py`

Optional only if test helpers become misleading:

- `src/continuous_refactoring/phases.py`

Do not refactor production control flow in this phase. Production edits should be limited to tiny bug fixes required by a newly added test, and any such fix must keep the public API stable.

## Instructions

1. Add focused tests for agent execution exceptions:
   - `maybe_run_agent` raises `ContinuousRefactorError`.
   - The outcome is failed with `call_role == "phase.execute"`.
   - Workspace rollback happens once to `head_before`.
   - The manifest on disk is unchanged.
   - The failure summary is sanitized through the existing decision helpers.
2. Add a test for nonzero agent exit:
   - `maybe_run_agent` returns a nonzero `CommandCapture`.
   - `read_status()` fallback behavior still drives `phase_reached` and summary.
   - `failure_kind == "agent-exited-nonzero"`.
   - Validation is not run.
3. Add a test for validation infrastructure failure:
   - `run_tests` raises `ContinuousRefactorError`.
   - Retry occurs when budget remains.
   - Terminal failure uses `failure_kind == "validation-infra-failure"`.
   - Retry context still uses `status_summary()` from the agent status, not raw test output.
4. Add a test for unlimited retry budget:
   - `max_attempts=None` keeps retrying validation failures until a later success.
   - The returned retry number matches the successful attempt.
   - Each failed validation attempt rolls back before retrying.
5. Add a test for stale or unknown phase completion:
   - Passing a `PhaseSpec` whose name is absent from `manifest.phases` raises `ContinuousRefactorError`.
   - The manifest file is not rewritten as complete.
6. Add a test that successful completion clears deferred state:
   - Start with `wake_up_on`, `awaiting_human_review`, `human_review_reason`, and `cooldown_until` set.
   - After success, all four are cleared and `last_touch` changes.
7. Keep tests outcome-oriented. Use monkeypatches only at real boundaries: `get_head_sha`, `revert_to`, `maybe_run_agent`, and `run_tests`.

## Definition of Done

- `tests/test_phases.py` explicitly covers agent exceptions, agent nonzero exits, validation infrastructure exceptions, unlimited retries, unknown phase completion, and deferred-state cleanup.
- No public symbol or monkeypatch path has changed.
- Existing phase execution behavior remains unchanged except for intentional bug fixes proven by the new tests.
- The repository is shippable after this phase.

## Validation

Run:

```sh
uv run pytest tests/test_phases.py
uv run pytest tests/test_loop_migration_tick.py tests/test_focus_on_live_migrations.py
```
