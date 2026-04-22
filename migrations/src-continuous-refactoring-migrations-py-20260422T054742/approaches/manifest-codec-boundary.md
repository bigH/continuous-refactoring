# Manifest Codec Boundary

## Strategy

Keep `src/continuous_refactoring/migrations.py` as the public migration-domain module, but extract manifest JSON parsing and serialization into a private focused module, likely `src/continuous_refactoring/migration_manifest_codec.py`.

`migrations.py` would keep:
- `MigrationManifest` and `PhaseSpec`
- path helpers
- phase cursor/completion functions
- wake-up eligibility functions
- public `load_manifest()` and `save_manifest()` boundary functions

The new codec module would own:
- validating raw JSON field types
- mapping legacy `ready_when` to `precondition`
- mapping legacy integer `current_phase` to a phase name
- checking phase-name uniqueness during decode/encode
- converting manifests to sorted, indented JSON payloads

`load_manifest()` and `save_manifest()` stay where callers already import them, but their bodies become thin boundary functions: read/write atomically, call decode/encode, and wrap low-level JSON or filesystem failures only when doing so improves the message.

## Tradeoffs

Pros:
- Best first cut. It removes the densest part of `migrations.py` without moving the public import surface.
- Keeps the module boundary domain-focused: `migrations.py` remains the place callers look for migration operations.
- Makes legacy manifest compatibility explicit and easier to delete later when no stored manifests need it.
- Allows tighter tests around raw payload decoding without touching the filesystem for every case.

Cons:
- Adds one internal module while keeping the public load/save functions in `migrations.py`.
- The split can feel small if the goal is fewer modules rather than clearer responsibilities.
- Some tests will still exercise codec behavior through `load_manifest()` because that is the real boundary.

## Estimated Phases

1. **Characterize codec behavior**
   - Add focused tests for malformed JSON, missing fields, duplicate phase names, legacy `ready_when`, legacy integer cursors, and unknown `current_phase`.
   - Keep existing roundtrip and atomic-write tests at the public `load_manifest()` / `save_manifest()` level.

2. **Extract decode/encode helpers**
   - Create `migration_manifest_codec.py` with private-ish public functions such as `decode_manifest_payload()` and `encode_manifest_payload()`.
   - Use frozen dataclasses from `migrations.py`; do not create parallel manifest types.
   - Preserve exact saved JSON formatting: `indent=2`, `sort_keys=True`, trailing newline.

3. **Tighten error boundaries**
   - Keep `ContinuousRefactorError` messages for schema failures stable enough for tests.
   - If JSON decoding fails, translate at `load_manifest()` with the manifest path in the message and preserve the original exception as `__cause__`.
   - Do not wrap internal pure helper failures twice.

4. **Retarget tests and exports**
   - Add `migration_manifest_codec` to `__init__._SUBMODULES` only if it exports symbols intentionally; otherwise keep it unexported.
   - Prefer tests through `migrations.load_manifest()` unless direct codec tests materially reduce setup noise.
   - Run `uv run pytest tests/test_migrations.py tests/test_planning.py tests/test_loop_migration_tick.py`, then `uv run pytest`.

## Risk Profile

Low-medium. The behavior is well covered and the public import paths can stay stable, but manifest compatibility is load-bearing for existing migration state.

Main watch-outs:
- Do not remove legacy `ready_when` or integer `current_phase` support in this migration.
- Do not create re-export shims or duplicate exported names in `__init__.py`.
- Preserve atomic write cleanup on failed replace.
- Preserve `current_phase=""` as the terminal/no-current-phase state.

## Best Fit

Choose this as the recommended approach. It cuts real complexity, keeps caller churn low, and names the highest-noise responsibility in `migrations.py`: manifest wire-format compatibility.
