# Command Module Split

## Strategy

Turn `cli.py` into a thin parser and dispatcher, then move command implementations into small command-focused modules:

- `init_cli.py` for project registration and live migration directory setup.
- `taste_cli.py` for taste workflows.
- `review_cli.py` for migration review workflows.
- Keep `run` and `run-once` wrappers in `cli.py` or move them to `run_cli.py` only after the parser namespace contract is characterized.

Avoid a framework-style registry. The command map can stay as a plain dictionary in `cli.py`, with imported handler functions.

## Why This Fits

The current module mixes unrelated domains. A command module split makes imports meaningful: config-heavy init behavior is not next to interactive taste editing, review manifest mutation is not next to parser type converters, and loop dispatch remains visible.

This is the broad structural option.

## Estimated Phases

1. Write a parser and dispatch characterization suite.
   - Cover subcommand parsing and default namespace fields.
   - Cover `_COMMAND_HANDLERS` behavior through `cli_main`, including stale taste warning.
   - Cover package import uniqueness after adding modules.

2. Extract `review_cli.py`.
   - Lowest state surface among the big command groups.
   - Move `_resolve_review_context`, list, perform, and review sub-dispatch.
   - Retarget review tests.

3. Extract `taste_cli.py`.
   - Move taste helpers and retarget taste tests.
   - Keep top-level stale warning in `cli.py`.

4. Extract `init_cli.py`.
   - Move `_handle_init`.
   - Keep parser construction in `cli.py`.

5. Reassess `run` wrappers.
   - If `cli.py` is already small and readable, leave them.
   - If not, create `run_cli.py` with targeting validation and loop error translation.

6. Full validation: `uv run pytest`.

## Tradeoffs

- Pros: ends with the cleanest module shape.
- Pros: command modules are easy for future agents to find and change.
- Pros: `cli.py` becomes mostly stable plumbing.
- Cons: largest blast radius.
- Cons: many private tests need coordinated updates.
- Cons: adding several modules increases package import surface and `__init__` uniqueness checks.

## Risk Profile

Medium-to-high.

Primary risks:
- Doing too much in one migration and mixing mechanical moves with behavior changes.
- Import cycles if command modules import parser helpers from `cli.py`.
- Test churn around private handlers obscuring real regressions.
- New module exports colliding through package root re-export.

Mitigation:
- Sequence one command family per phase.
- New command modules should not import `cli.py`; `cli.py` imports them.
- Keep `__all__` narrow and avoid re-exporting private helpers.
- Run focused tests after each extraction, then full pytest at the end.

## Must Preserve

- Argparse remains the CLI parser. No command DSL.
- `build_parser()` remains the parser construction entry point.
- `cli_main()` remains the console entry point.
- Command handler map remains patchable enough for existing warning/dispatch tests or tests are updated intentionally.
- No runtime dependencies.

## When To Choose This

Choose this only if the migration is allowed to be multi-phase and the caller values the final module structure more than minimal diff size. For a one-phase migration, this is too much.
