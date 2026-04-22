# Review And Run Boundary

## Strategy

Improve `cli.py` by isolating the two places where command handling crosses into other subsystems: migration review and loop execution.

Extract review behavior into `review_cli.py`. Then tighten run dispatch in place by making targeting validation and loop error translation more explicit, without moving the whole run path away from `cli.py`.

This keeps the refactor close to the selected local cluster: `cli.py`, `loop.py`, `migrations.py`, `prompts.py`, `artifacts.py`, and `agent.py`.

## Why This Fits

Review is a migration-domain command pretending to live in the generic CLI module. It reads manifests, resolves phases, composes review prompts, launches an agent, and mutates review state. That is exactly the kind of behavior a domain-focused boundary should own.

Run handling is smaller but fragile. It should stay visible because it defines the CLI guard contract before handing to `loop.py`.

## Estimated Phases

1. Characterize review command behavior.
   - Parser accepts `review`, `review list`, and `review perform`.
   - List filters only flagged migrations.
   - Missing project/live-dir exits with correct codes.
   - Perform rejects missing/unflagged migrations.
   - Perform runs agent, requires `awaiting_human_review` to clear, and removes stale `human_review_reason`.

2. Extract `review_cli.py`.
   - Export `handle_review`.
   - Move review context resolution and list/perform helpers.
   - Keep parser construction in `cli.py`.
   - Retarget review tests to the new module.

3. Clarify run boundary in `cli.py`.
   - Keep `_validate_targeting`, `_handle_run_once`, `_handle_run`, and `_run_with_loop_errors` together.
   - Optionally rename private helpers if tests are updated in the same phase.
   - Do not change targeting precedence; `loop.py` and targeting modules own actual resolution.

4. Validate focused surfaces.
   - `uv run pytest tests/test_cli_review.py tests/test_focus_on_live_migrations.py tests/test_run.py tests/test_cli_taste_warning.py`.
   - Then `uv run pytest`.

## Tradeoffs

- Pros: smaller and safer than a broad command split.
- Pros: removes migration-specific imports from `cli.py`.
- Pros: keeps the fragile run guard code easy to see.
- Cons: line-count reduction is moderate.
- Cons: taste remains the largest body inside `cli.py`.
- Cons: may feel incomplete if the migration goal is to make `cli.py` genuinely small.

## Risk Profile

Medium-low.

Primary risks:
- `review perform` side effects are easy to subtly alter.
- Tests patch `continuous_refactoring.cli.run_agent_interactive` and private review helpers today.
- Moving review helpers can make stderr/exit-code behavior drift.

Mitigation:
- Extract review mechanically.
- Retarget monkeypatch paths deliberately.
- Assert manifest outcomes rather than internal calls.
- Leave run behavior in place except for naming and grouping cleanup.

## Must Preserve

- Review usage text: `Usage: continuous-refactoring review {list,perform}`.
- Review list output columns and tab separation.
- `review list` uses exit code 1 for missing project/live-dir; `review perform` uses exit code 2 for command/setup errors.
- `review perform` invokes the interactive agent from repo root.
- Loop errors still translate to `SystemExit(1)` at the CLI boundary.
