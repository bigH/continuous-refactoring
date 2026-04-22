# Phase 2: Extract Manifest Codec

## Objective

Move pure manifest payload decoding and encoding into `src/continuous_refactoring/migration_manifest_codec.py` while keeping `migrations.py` as the public migration API boundary.

## Precondition

Phase 1 is complete: focused tests characterize legacy `ready_when`, `precondition` precedence, missing phase preconditions, integer and empty current-phase compatibility, unknown current phases, duplicate phase names, exact JSON formatting, and failed atomic replace cleanup. Those tests pass with all manifest codec logic still implemented in `src/continuous_refactoring/migrations.py`.

## Scope

Allowed production files:

- `src/continuous_refactoring/migrations.py`
- `src/continuous_refactoring/migration_manifest_codec.py`

Allowed test files:

- `tests/test_migrations.py`
- `tests/test_continuous_refactoring.py` only if package import behavior needs coverage

Do not edit planning, phase execution, prompts, loop, CLI, or package-root exports unless the extraction reveals a real stale contract.

## Instructions

1. Create `src/continuous_refactoring/migration_manifest_codec.py`.
   - Include `from __future__ import annotations`.
   - Use full-path imports only.
   - Define explicit module-local `__all__`, expected to be `("decode_manifest_payload", "encode_manifest_payload")`.
2. Keep `MigrationManifest`, `PhaseSpec`, `MigrationStatus`, and `MIGRATION_STATUSES` in `migrations.py`.
3. Avoid the circular-import trap:
   - Leave dataclass and status definitions near the top of `migrations.py`.
   - Import `decode_manifest_payload` and `encode_manifest_payload` from the codec only after those definitions.
   - Let the codec import the dataclasses and status constants from `continuous_refactoring.migrations`.
4. Move pure validation and conversion helpers into the codec:
   - status validation
   - mapping/object/string/bool requirements
   - phase precondition extraction
   - phase list decoding
   - duplicate phase-name validation
   - legacy integer current-phase mapping
   - current-phase validation
   - manifest-to-JSON encoding
5. Keep migration behavior helpers in `migrations.py`:
   - `_phase_index`
   - `has_executable_phase`
   - `resolve_current_phase`
   - `advance_phase_cursor`
   - `complete_manifest_phase`
   - path helpers
   - wake-up helpers
6. Update `load_manifest(path)`:
   - Read text from disk.
   - Parse JSON.
   - Call `decode_manifest_payload(raw)`.
   - Keep the public function name and return type unchanged.
7. Update `save_manifest(manifest, path)`:
   - Call `encode_manifest_payload(manifest)` before creating `path.parent`.
   - Preserve the existing atomic write structure.
   - Preserve cleanup of the temp file when replace fails.
8. Do not add `migration_manifest_codec` to `src/continuous_refactoring/__init__.py` `_SUBMODULES`.
9. Retarget tests only where direct codec tests remove filesystem noise. Keep load/save tests for public boundary behavior, formatting, and atomic writes.

## Definition of Done

- `migration_manifest_codec.py` owns manifest payload decode/encode and has an explicit module-local `__all__`.
- `migrations.py` no longer contains raw manifest schema validation or JSON encoding helpers.
- `MigrationManifest`, `PhaseSpec`, `load_manifest()`, and `save_manifest()` remain importable from `continuous_refactoring.migrations`.
- `migration_manifest_codec` is not listed in package-root `_SUBMODULES`.
- Phase 1 characterization tests still pass without behavior changes.
- The repository is shippable after this phase.

## Validation

Run:

```sh
uv run pytest tests/test_migrations.py
```

If package import/export coverage is added or touched, also run:

```sh
uv run pytest tests/test_continuous_refactoring.py
```
