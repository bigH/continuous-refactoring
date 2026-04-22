# Taste Command Extraction

## Strategy

Extract the `taste` workflow from `cli.py` into a focused module, likely `continuous_refactoring.taste_cli`.

Leave parser construction and top-level dispatch in `cli.py`. Move taste path resolution, mode selection, agent flag validation, interview/refine/upgrade handlers, settle-path handling, and `_TASTE_MODE_HANDLERS` into the new module. `cli.py` imports one public handler, for example `handle_taste`, and wires it into `_COMMAND_HANDLERS`.

The new module should own taste-specific boundary errors and keep `ContinuousRefactorError` translation near the interactive agent boundary.

## Why This Fits

Taste behavior is the largest cohesive subdomain inside `cli.py`. It has its own prompts, config helpers, state transitions, overwrite policy, settle protocol, and tests. Pulling it out makes `cli.py` read like a real CLI boundary instead of a mixed command implementation file.

This is the highest-value extraction if the migration goal is meaningful size reduction.

## Estimated Phases

1. Add characterization tests for the taste matrix.
   - Plain project/global path.
   - Missing agent flags.
   - `--force` allowed only with `--interview`.
   - Interview backup behavior.
   - Refine fallback to default taste.
   - Upgrade current-version no-op and missing flags for stale taste.
   - Agent failure, nonzero exit, empty output, and settle cleanup.

2. Create `src/continuous_refactoring/taste_cli.py`.
   - Include `from __future__ import annotations`, explicit `__all__`, full-path imports.
   - Export only the handler needed by `cli.py`, unless tests intentionally import more.
   - Keep runtime dependencies stdlib-only.

3. Retarget tests.
   - Patch `continuous_refactoring.taste_cli.run_agent_interactive_until_settled` instead of `continuous_refactoring.cli...`.
   - Prefer testing `handle_taste` through `build_parser()` where practical.

4. Simplify `cli.py`.
   - Remove taste implementation helpers from `cli.py`.
   - Keep parser flags in `cli.py`.
   - Wire command dispatch to the extracted handler.

5. Validate.
   - `uv run pytest tests/test_cli_init_taste.py tests/test_taste_interview.py tests/test_taste_refine.py tests/test_taste_upgrade.py tests/test_cli_taste_warning.py tests/test_continuous_refactoring.py`.

## Tradeoffs

- Pros: cleanest domain boundary; biggest line-count win; isolates stateful taste workflows from parser wiring.
- Pros: aligns FQNs with behavior: `taste_cli` owns taste CLI behavior.
- Cons: many tests currently monkeypatch symbols through `continuous_refactoring.cli`; retargeting is noisy.
- Cons: package `__init__` may need to import/re-export the new module if its public exports matter, which risks duplicate symbols.

## Risk Profile

Medium.

Primary risks:
- Breaking monkeypatch paths for agent handoff tests.
- Accidentally changing when `--upgrade` requires agent flags.
- Losing settle-file cleanup or backup semantics.
- Adding a public export that collides in package `__init__`.

Mitigation:
- Keep the new module's `__all__` intentionally tiny.
- Move code mechanically first, then improve names.
- Run the taste-specific tests before broad cleanup.

## Must Preserve

- Existing parser spelling: `taste --global`, `--interview`, `--upgrade`, `--refine`, `--with`, `--model`, `--effort`, `--force`.
- `taste --upgrade` may return without agent flags when taste is already current.
- `--force` only applies to interview.
- Interactive taste agent still uses the settle protocol through `run_agent_interactive_until_settled`.
- Stale taste warning remains top-level in `cli_main`, not hidden inside taste handling.
