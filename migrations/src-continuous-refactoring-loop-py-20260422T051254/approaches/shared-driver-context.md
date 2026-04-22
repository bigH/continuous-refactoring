# Shared Driver Context

## Strategy

Introduce a small frozen value object for resolved runtime settings, then use it to trim repetition inside `loop.py` before moving larger blocks.

Example shape:

- `DriverSettings`
  - `repo_root`
  - `timeout`
  - `sleep_seconds`
  - `max_attempts`
  - `taste`
  - `validation_command`
  - `commit_message_prefix`
- `build_driver_settings(args, *, default_timeout, include_sleep)`
- focused helpers for `create_run_artifacts()` and target selection if they read better after settings exist

This is not a framework and not an interface. It is a typed bundle for values currently recomputed across `run_once()`, `run_loop()`, and `run_migrations_focused_loop()`.

The end state can keep all three public functions in `loop.py`, but make them shorter and less error-prone by removing duplicated setup and status plumbing.

## Tradeoffs

Pros:
- Lowest behavioral risk.
- Tightens types around argparse-derived values without changing user-facing behavior.
- Makes later extraction easier because function signatures shrink.
- Good place to clarify `--max-attempts 0` normalization and timeout defaults.

Cons:
- Does not remove the biggest block by itself.
- A settings object can become a junk drawer if it includes values only one mode needs.
- May add indirection without enough payoff unless paired with small helper deletions.
- Still leaves `loop.py` large after completion.

## Estimated Phases

1. **Pin argument normalization behavior**
   - Add focused tests for max-attempt defaults, unlimited retry warning, timeout defaults, and sleep parsing impact where coverage is thin.
   - Validation: `uv run pytest tests/test_run.py tests/test_focus_on_live_migrations.py`.

2. **Add settings value object**
   - Create a frozen dataclass in `loop.py` or a new `driver_settings.py`.
   - Prefer keeping it private inside `loop.py` first unless another module immediately benefits.
   - Replace repeated local setup in the smallest mode first, likely `run_migrations_focused_loop()`.

3. **Apply to normal loop and run-once**
   - Use settings to remove duplicated `_effective_max_attempts()`, timeout, taste, and validation-command plumbing.
   - Keep mode-specific values explicit when bundling would hide behavior.

4. **Follow-up extraction decision**
   - Reassess whether `refactor_attempt.py` extraction is now simpler.
   - If yes, make that the next migration rather than adding more context objects.
   - Run `uv run pytest`.

## Risk Profile

Low. This is mostly structure around already-computed values.

Main watch-outs:
- Avoid putting mutable collaborators or artifact instances into a settings object unless lifetime is obvious.
- Keep `run_once()`'s `commit_message_prefix` behavior exact: it currently routes migrations with `"continuous refactor"` and commits ordinary one-shot work as `"continuous refactor: run-once"`.
- Do not make `DriverSettings` public unless there is a real external use.
- Comments should stay near zero; field names should carry the meaning.

## Best Fit

Choose this if the team wants a low-risk preparatory migration. It is useful as phase 1 before a larger split, but weak as the whole migration because it does not remove the main orchestration knot.
