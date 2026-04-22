# Phase 3: Tighten I/O Boundaries

## Objective

Make `load_manifest()` and `save_manifest()` the only places that translate low-level JSON and filesystem failures into `ContinuousRefactorError`, while letting pure codec schema errors bubble unchanged.

## Precondition

Phase 2 is complete: `src/continuous_refactoring/migration_manifest_codec.py` exists, owns manifest payload decode/encode, has module-local `__all__`, is not listed in `__init__._SUBMODULES`, and `migrations.py` delegates `load_manifest()` / `save_manifest()` payload work to it. All Phase 2 validation commands pass.

## Scope

Allowed production files:

- `src/continuous_refactoring/migrations.py`
- `src/continuous_refactoring/migration_manifest_codec.py` only if a pure codec error needs a clearer message

Allowed test files:

- `tests/test_migrations.py`

Do not change the manifest dataclasses, saved JSON fields, or compatibility rules in this phase.

## Instructions

1. Add tests for malformed JSON at the public boundary:
   - `load_manifest(path)` raises `ContinuousRefactorError`.
   - The message includes the manifest path and indicates the manifest could not be loaded or parsed.
   - The original `json.JSONDecodeError` is preserved as `__cause__`.
2. Add tests for filesystem read failure:
   - Use a real failing path shape, such as passing a directory where a file is expected.
   - `load_manifest(path)` raises `ContinuousRefactorError`.
   - The original `OSError` subclass is preserved as `__cause__`.
3. Add or tighten tests for filesystem write/replace failure:
   - `save_manifest(manifest, path)` raises `ContinuousRefactorError` for replace failure.
   - The original exception is preserved as `__cause__`.
   - Temporary files are still cleaned up.
4. Add a test that codec schema errors are not double wrapped:
   - Unknown status, missing required field, duplicate phase names, or unknown current phase still raises the codec's `ContinuousRefactorError`.
   - The message remains about the schema problem, not a generic I/O wrapper.
5. Implement boundary wrapping in `migrations.py`:
   - Wrap `json.JSONDecodeError` from `json.loads`.
   - Wrap low-level `OSError` from `read_text`, `mkdir`, temp file creation, writing, replace, or unlink cleanup only where useful.
   - Use exception nesting with `raise ContinuousRefactorError(...) from error`.
   - Do not catch and re-wrap `ContinuousRefactorError` from the codec.
6. Preserve validation order in `save_manifest()`:
   - Encode first.
   - Create parent directory second.
   - Write temp file third.
   - Replace last.
   - Cleanup temp file on replace failure.

## Definition of Done

- Malformed JSON and filesystem read/write failures are translated at `load_manifest()` / `save_manifest()` with useful path-bearing `ContinuousRefactorError` messages and preserved causes.
- Pure manifest schema failures from the codec still surface directly as `ContinuousRefactorError` without a generic wrapper.
- Atomic write cleanup still removes temp files after replace failure.
- Invalid manifest data rejected before encoding still does not create the destination directory.
- Manifest compatibility and saved JSON formatting remain unchanged.
- The repository is shippable after this phase.

## Validation

Run:

```sh
uv run pytest tests/test_migrations.py
```
