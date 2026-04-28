# In-Place Config Hygiene Sweep

## Strategy

Keep the public shape of `continuous_refactoring.config` intact and refactor behavior inside one module. The migration is a cleanup batch centered on clarity and failure-surface consistency.

The concrete moves are:
- Add small private helpers in `config.py` for payload read and write steps so manifest/taste handling has one obvious path.
- Normalize all manifest and taste parsing failures to `ContinuousRefactorError` at the boundary where config file content is interpreted.
- Reduce defensive branching in `find_project`, `_entry_from_dict`, and live-migrations path checks into explicit helper predicates.
- Add stronger tests around malformed manifest payloads/permission failures while preserving existing callsites.

This approach aligns with the taste note to avoid churn in a wide module: no new modules, no rollout flags, no compatibility indirection.

## Tradeoffs

Pros:
- Lowest churn across `loop.py`, `cli.py`, `prompts.py`, `agent.py`, `artifacts.py`, and `git.py` because imports and API names stay the same.
- Fastest migration path and easiest rollback if behavior drifts.
- Directly improves test-backed behavior in the surface currently validated by `tests/test_config.py` and CLI-based config tests.

Cons:
- Long-term domain pressure remains: manifest persistence, taste parsing, and project registration still cohabit one module.
- Keeps one module as a larger cognitive boundary, which may limit future extraction.

## Estimated Phases

1. Baseline lock-in and test hardening
   - Add/extend tests for JSON decode errors and filesystem exceptions in `tests/test_config.py`.
   - Add explicit checks that `load_manifest`/`save_manifest` preserve error causality.

2. Refactor config internals
   - Introduce a single read/validate/deserialize path for project manifest.
   - Preserve stable public functions and names in `__all__`.
   - Keep module-level constants and dataclasses as-is.

3. Behavioral tightening
   - Ensure `_detect_git_remote` and `resolve_live_migrations_dir` path checks stay exception-safe and side-effect-light.
   - Eliminate dead or duplicate error message branches.

4. Validation pass
   - Run `uv run pytest tests/test_config.py tests/test_cli_upgrade.py tests/test_cli_init_taste.py tests/test_taste_refine.py tests/test_taste_interview.py`.

## Risk Profile

Low risk. Main risk is under-validating boundary failures currently hidden by raw parser exceptions and altering error text relied upon by tests.

Watch-outs:
- Keep exact wording compatibility for existing user-facing messages unless tests or behavior contracts are updated intentionally.
- Ensure temporary files are still always unlinked on partial-write failures.

