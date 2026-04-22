# Characterize Then Slice

## Strategy

Pin the observable CLI contract first, then make the smallest extractions that reduce `cli.py` without changing its public boundary.

Keep `continuous_refactoring.cli` as the user-facing module exporting `build_parser`, `cli_main`, `parse_max_attempts`, and `parse_sleep_seconds`. Add characterization tests around parser defaults, dispatch, exit codes, stale taste warnings, and run guard behavior. After that, extract only helper groups that are already cohesive and low-risk.

Recommended first seam: move review helpers or taste helpers after tests are in place, while preserving temporary compatibility aliases in `cli.py` for private tests only until the same migration updates tests.

## Why This Fits

`cli.py` is 750 lines, but its real risk is not size. The risk is hidden command-line behavior: stderr text, `SystemExit` codes, namespace field names consumed by `loop.py`, and test monkeypatch paths. Characterization keeps the refactor honest.

This is the safest default approach.

## Estimated Phases

1. Characterize parser and dispatch behavior.
   - Cover every subcommand and core defaults.
   - Pin `--max-attempts`, `--sleep`, focus mode, `repo_root`, stale taste warning, and no-command behavior.
   - Validation: `uv run pytest tests/test_cli_taste_warning.py tests/test_run.py::test_cli_does_not_cap_max_refactors tests/test_focus_on_live_migrations.py`.

2. Extract one cohesive command workflow.
   - Pick `review` first if optimizing for low blast radius.
   - Pick `taste` first if optimizing for line-count reduction.
   - Preserve `cli.py` as the dispatch boundary.

3. Retarget tests from private `continuous_refactoring.cli._handle_*` imports to the new owning module, or keep deliberate compatibility names in `cli.py` only for handlers that are still dispatch entry points.

4. Run full validation and update `AGENTS.md` only if the final module layout changes a documented invariant.

## Tradeoffs

- Pros: lowest regression risk; produces useful tests even if implementation stops early; respects shipped CLI compatibility.
- Pros: avoids speculative command registries or argparse wrappers.
- Cons: first phase does not reduce production code.
- Cons: may leave `cli.py` still fairly large after one migration.

## Risk Profile

Low-to-medium.

Primary risks:
- Characterization tests can overfit exact argparse formatting.
- Compatibility aliases can become dead weight if not removed in the same migration.
- A partial extraction may improve tests more than structure.

Mitigation:
- Assert outcomes and key messages, not full help text.
- Treat compatibility names as migration scaffolding, not permanent API.
- Keep extraction to one command family per phase.

## Must Preserve

- `continuous_refactoring.cli.__all__` stays unique under package re-export.
- `python -m continuous_refactoring` still invokes `cli_main`.
- Stale taste warning fires once for any subcommand, never for bare help/no command, and preserves handler exit behavior.
- `run` guard semantics: focus mode bypasses targeting and `--max-refactors`; non-focus mode does not.
- `run-once` requires targeting or `--scope-instruction`.
