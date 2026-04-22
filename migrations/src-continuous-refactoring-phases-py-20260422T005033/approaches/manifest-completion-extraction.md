# Manifest Completion Extraction

## Strategy

Move phase-completion manifest mutation out of `execute_phase()` and into `migrations.py`, where cursor and manifest invariants already live.

The new helper would own:

- locating the completed phase by name
- setting `done=True`
- clearing deferral and human-review fields
- advancing `current_phase`
- marking the migration `done` when no next phase exists

`phases.py` would still run the agent and validation. After validation passes, it would call a migration-domain helper such as `complete_phase(manifest, phase.name, now)` and then `save_manifest()`.

## Tradeoffs

Pros:
- Moves manifest invariants to the module that already owns manifest loading, saving, cursor advancement, and phase-name validation.
- Makes `execute_phase()` less responsible for persistence rules.
- Easier to test completion behavior without agent/test/git setup.
- Reduces the chance that future manifest fields are cleared inconsistently.

Cons:
- Only removes the tail of `execute_phase()`; the retry loop remains large.
- Adds another exported migration helper, increasing package surface.
- Could be too narrow if the migration goal is primarily execution-flow readability.
- Needs careful naming to avoid implying file I/O when the helper only transforms a manifest.

## Estimated Phases

1. **Characterize manifest completion**
   - Add `tests/test_migrations.py` coverage for completing a middle phase, completing the final phase, unknown phase failure, and cleanup of `wake_up_on`, `awaiting_human_review`, `human_review_reason`, and `cooldown_until`.
   - Keep existing `tests/test_phases.py` integration tests intact.

2. **Add migration-domain helper**
   - Implement a pure helper in `migrations.py`, likely returning a new `MigrationManifest`.
   - Reuse `advance_phase_cursor()` and existing phase-name validation.
   - Export it only if `phases.py` imports it directly.

3. **Replace inline completion in `phases.py`**
   - Remove manual phase-index search and inline `replace()` cascade.
   - Save the returned manifest at the existing manifest path.
   - Run `uv run pytest tests/test_migrations.py tests/test_phases.py`.

4. **Follow-up execution cleanup**
   - If `execute_phase()` still reads poorly, do a smaller in-place helper extraction afterward.
   - Run `uv run pytest`.

## Risk Profile

Low to medium risk. The extraction is focused and tests can pin the resulting manifest exactly.

Main watch-outs:
- The helper should be pure and not write files; `save_manifest()` already owns persistence.
- Do not duplicate cursor logic already in `advance_phase_cursor()`.
- Do not rename manifest fields or change JSON shape.
- Keep legacy `ready_when` compatibility in `load_manifest()` untouched unless a separate migration removes it with evidence.

## Best Fit

Choose this as a small first phase before the in-place pipeline if manifest completion feels like the cleanest separable responsibility. Alone, it is useful but not enough to make `phases.py` substantially clearer.
