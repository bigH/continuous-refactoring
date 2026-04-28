# Mode-Split Runner Modules

## Strategy

Turn `loop.py` into a thin coordination surface by splitting orchestration by runner mode.

Likely module shape:
- `run_once_runner.py` for one-shot execution
- `run_loop_runner.py` for target-driven looping
- `migration_focus_runner.py` for focused live-migration execution
- `loop.py` as a compatibility-facing entry module exporting the same public functions

Shared mechanics should move only if truly shared and coherent, likely into one small support module for:
- effort budget resolution/logging
- common baseline validation
- commit finalization

Do not split into an anemic forest of helper modules. Three runner modules plus one shared support module is already enough.

## Tradeoffs

Pros:
- Strongest improvement to file size and FQN usefulness.
- Matches the actual product shape: there are three runner modes with overlapping but different control flow.
- Makes future work on a single mode less risky and easier to review.

Cons:
- Highest migration churn.
- Requires careful handling of shared behavior so it is not duplicated badly or abstracted into sludge.
- Test monkeypatch paths and import wiring will move in many places.
- `__init__.py` export uniqueness and package surface need deliberate review.

## Estimated Phases

1. Clarify shared vs mode-specific responsibilities in place.
   `required_effort: medium`
   - Identify what must remain identical across modes:
   - clean-worktree guard
   - baseline validation
   - artifact lifecycle
   - effort budget logging
   - commit ownership
   - Define what is intentionally mode-specific instead of chasing perfect reuse.

2. Extract one runner first: focused live migrations.
   `required_effort: high`
   - Move `run_migrations_focused_loop()` and `_focus_eligible_manifests()` first.
   - This is the safest initial split because it already has the clearest bounded purpose.

3. Extract target-driven `run_loop()`.
   `required_effort: high`
   - Move migration probe + target action sequencing into `run_loop_runner.py`.
   - Keep retry-attempt internals local unless a separate attempt module has already proven worthwhile.

4. Extract `run_once()` last and reduce `loop.py` to exports and thin delegation.
   `required_effort: medium`
   - Keep public API stable: `continuous_refactoring.loop.run_once`, `run_loop`, `run_migrations_focused_loop`.
   - No re-export shim games beyond the entry module still owning these public functions.

5. Validate imports and behavior.
   `required_effort: medium`
   - `uv run pytest tests/test_run_once.py tests/test_run.py tests/test_focus_on_live_migrations.py tests/test_loop_migration_tick.py tests/test_e2e.py`
   - `uv run pytest`

## Risk Profile

Medium-to-high.

Main risks:
- Splitting on paper instead of along truthful behavior boundaries.
- Shared support module growing into a junk drawer.
- Regressing tests that patch internals under `continuous_refactoring.loop`.

Mitigations:
- Extract the focused-migration runner first as a proof that the split is real.
- Keep `loop.py` as the stable public entry surface.
- Prefer a little duplication over a fake “shared” abstraction that hides behavior.

## Best Fit

Choose this when the migration goal is structural, not cosmetic. This is the best long-term design if the repo is willing to absorb a real multi-phase refactor.
