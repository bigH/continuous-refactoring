# Domain Split: Manifest Core and Taste Core

## Strategy

Split `config.py` into two domain modules: one focused on durable project manifest and live-migrations metadata, and one focused on taste text/version behavior.

Proposed new structure:
- `config_manifest.py`: `ProjectEntry`, `ResolvedProject`, manifest path helpers, `_load_manifest_payload`, load/save manifest I/O, `find_project`, `register_project`, `resolve/set project` APIs.
- `config_taste.py`: `TASTE_CURRENT_VERSION`, `_DEFAULT_TASTE`, parser helpers, `load_taste`, `ensure_taste_file`, `taste_is_stale`.
- `config.py`: minimal façade that re-exports the stable names consumed by existing modules, avoiding external API breakage during this migration.

This is consistent with taste-scoping-version guidance: split where concerns are truly stable and frequently crossed.

## Tradeoffs

Pros:
- Improves domain clarity without changing external call signatures.
- Makes independent test growth natural: manifest tests and taste tests can evolve separately.
- Makes future migration of either piece easier and safer.

Cons:
- Immediate import churn in this migration: `loop.py`, `cli.py`, `review_cli.py`, `prompts.py`, and tests touching config internals need updates in same cycle.
- The facade in `config.py` can become a de-facto compatibility layer if not kept minimal.
- Higher coordination cost across `test_cli_*` and `test_taste_*` modules.

## Estimated Phases

1. Create manifest module
   - Move manifest dataclasses and manifest functions out of `config.py`.
   - Add module tests under `tests/test_config.py` for moved behavior.

2. Create taste module
   - Move taste constants and helpers.
   - Keep prompt tests using `TASTE_CURRENT_VERSION` and `default_taste_text()` behavior unchanged.

3. Introduce intentional façade in `config.py`
   - Re-export stable symbols only.
   - Keep names verbatim for one-shot migration safety.

4. Callsite updates and test sweep
   - Replace direct imports in touched modules with explicit module imports where behavior is clearly domain-owned.
   - Run full affected suites: config, CLI taste/upgrade, and loop/targeted migration smoke tests.

## Risk Profile

Medium risk. Main risk is import churn and accidental divergence between façade exports and internal modules.

Watch-outs:
- Guard against accidental re-export aliasing; preserve existing symbol names.
- Avoid adding compatibility aliases with weak names like `new`, `temp`, or generic migration labels.
- Do not gate rollout; this is direct-wide change in a single project.

## Best Fit

Best for cleanup that should outlive repeated one-off edits and where future work is expected to touch manifest/taste independently.

