# Phase 1: Characterize Codec Contracts

## Objective

Lock down the manifest wire-format behavior before extracting it from `migrations.py`.

This phase should make the compatibility contract explicit without changing production structure.

## Precondition

The migration has not created `src/continuous_refactoring/migration_manifest_codec.py` yet. `MigrationManifest`, `PhaseSpec`, `load_manifest()`, `save_manifest()`, and all manifest validation helpers still live in `src/continuous_refactoring/migrations.py`, and the existing `tests/test_migrations.py` suite passes.

## Scope

Allowed files:

- `tests/test_migrations.py`

Optional only if a characterization test exposes an existing bug:

- `src/continuous_refactoring/migrations.py`

Do not create the codec module in this phase. Do not move helpers.

## Instructions

1. Add or tighten tests for legacy phase readiness fields:
   - A phase with only legacy `ready_when` loads with `PhaseSpec.precondition`.
   - A phase with both `precondition` and `ready_when` uses `precondition`.
   - A phase with neither field is rejected.
2. Add or tighten tests for current-phase compatibility:
   - `current_phase=""` loads successfully even when phases exist.
   - In-range legacy integer `current_phase` maps to the phase name.
   - Out-of-range legacy integer `current_phase` maps to `""`.
   - Legacy integer `current_phase` with no phases maps to `""`.
   - Boolean `current_phase` is rejected even though `bool` is an `int` subclass.
   - Unknown string `current_phase` is rejected.
3. Add or tighten duplicate phase-name tests:
   - Duplicate names are rejected on load.
   - Duplicate names are rejected on save before replacing the manifest.
4. Add or tighten JSON-format tests:
   - Saved bytes exactly equal `json.dumps(parsed, indent=2, sort_keys=True) + "\n"`.
   - Saved phase payloads contain `precondition`.
   - Saved phase payloads do not contain `ready_when`.
5. Add a failed atomic replace cleanup test:
   - Force the replace step in `save_manifest()` to fail.
   - Assert the temporary `*.tmp` file is removed.
   - Assert the final manifest path is absent or unchanged.
6. Keep tests outcome-oriented. Use `tmp_path` and real JSON files. Use monkeypatching only at the filesystem boundary for the failed replace case.
7. Do not add expectations for new JSON decode wrapping yet. That is Phase 3.

## Definition of Done

- `tests/test_migrations.py` explicitly covers legacy `ready_when`, `precondition` precedence, missing phase preconditions, integer and empty current-phase compatibility, unknown current phases, duplicate phase names, exact JSON formatting, and failed atomic replace cleanup.
- Production code is unchanged except for intentional bug fixes proven by the new tests.
- No public symbol, import path, manifest field, or JSON output format has changed.
- The repository is shippable after this phase.

## Validation

Run:

```sh
uv run pytest tests/test_migrations.py
```
