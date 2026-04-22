# Phase 1: Characterize Review Contracts

## Objective

Lock down `continuous-refactoring review` behavior before moving it out of `cli.py`.

This phase should improve confidence, not structure. Production code must stay still. If characterization exposes a real production bug, stop and split a dedicated bug-fix phase before continuing this migration.

## Precondition

`src/continuous_refactoring/cli.py` still owns `_handle_review`, `_handle_review_list`, `_handle_review_perform`, `_resolve_review_context`, `_REVIEW_USAGE`, and the `run_agent_interactive` import used by review tests. `src/continuous_refactoring/review_cli.py` does not exist. The current review tests pass.

## Scope

Allowed files:

- `tests/test_cli_review.py`

Do not create `review_cli.py` in this phase. Do not retarget imports to a future module.

## Instructions

1. Review the existing `tests/test_cli_review.py` coverage and fill only meaningful gaps.
2. Ensure parser coverage includes:
   - `review` with no subcommand.
   - `review list`.
   - `review perform <migration> --with <agent> --model <model> --effort <effort>`.
3. Ensure list coverage asserts observable output:
   - only flagged migrations are listed;
   - output is tab-separated and ordered by migration directory name;
   - status, phase file, phase name, last touch, and reason columns are preserved;
   - absent review reasons render as `(no reason recorded)`;
   - absent current phases render `(none)` for phase file and phase name.
4. Ensure setup-error coverage distinguishes exit codes:
   - `review list` missing project or missing live migrations dir exits 1;
   - `review perform` missing project or missing live migrations dir exits 2.
5. Ensure perform coverage asserts outcomes:
   - missing migration exits 2;
   - unflagged migration exits 2;
   - agent nonzero return exits with that code;
   - agent success with `awaiting_human_review` still set exits 1;
   - happy path includes human review reason and current phase details in the prompt;
   - happy path invokes the agent from `Path.cwd().resolve()`;
   - happy path clears stale `human_review_reason` after `awaiting_human_review` is cleared.
6. Keep monkeypatching limited to the actual interactive-agent boundary. Prefer real manifests, real project registration, and real migration files.
7. Do not assert call choreography inside migration helpers. Assert printed output, exit codes, prompt content, agent repo root, and manifest state.
8. If a new characterization test exposes behavior that appears wrong, mark this phase blocked and propose a separate bug-fix phase. Do not repair it inside this characterization phase.

## Definition of Done

- `tests/test_cli_review.py` explicitly covers parser wiring, list filtering/output, setup error codes, perform rejection paths, agent failure behavior, the incomplete-review guard, prompt inputs, repo-root agent invocation, and stale reason cleanup.
- Production code is unchanged.
- No review behavior, parser flag, output column, exit code, or manifest side effect has changed.
- The repository is shippable after this phase.

## Validation

Run:

```sh
uv run pytest tests/test_cli_review.py
```
