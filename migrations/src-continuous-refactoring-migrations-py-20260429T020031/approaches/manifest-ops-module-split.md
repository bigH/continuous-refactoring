# Approach: Manifest Ops Split

## Strategy
- Keep `migrations.py` as the public compatibility facade for migration concepts, but move operational logic into a new internal module such as `src/continuous_refactoring/migration_manifest_ops.py`.
- Split responsibilities like this:
  - `migrations.py`: `MigrationManifest`, `PhaseSpec`, status vocabulary, stable exported helpers.
  - `migration_manifest_ops.py`: phase lookup, cursor advance, completion, eligibility, load/save helpers.
  - `migration_manifest_codec.py`: payload decoding/encoding only.
- Update internal callers gradually to import from the new ops module only where doing so improves readability. Keep the old `continuous_refactoring.migrations` imports working during the migration.

## Tradeoffs
- Better domain boundaries without changing the user-facing manifest structure or CLI behavior.
- Stronger long-term shape: codec stops pretending to be half the domain while `migrations.py` stops being a junk drawer.
- More churn than the in-place approach because many modules import from `migrations.py`.
- Requires discipline to avoid creating a pointless facade plus wrapper soup.

## Estimated phases
1. Add import-safe regression tests around the current `continuous_refactoring.migrations` surface and behavior-heavy tests in `tests/test_migrations.py`.
   - `required_effort`: `low`
2. Introduce `migration_manifest_ops.py` and move pure-ish operational helpers there without changing behavior.
   - `required_effort`: `medium`
3. Re-export the moved helpers from `migrations.py` so existing callers still work, then simplify internal call sites where direct ops imports are clearer.
   - `required_effort`: `medium`
4. Tighten error translation so filesystem and JSON wrapping stay at the true boundary, with nested causes preserved.
   - `required_effort`: `medium`
5. Run full pytest and decide whether any remaining direct imports should stay for compatibility or move for clarity.
   - `required_effort`: `low`

## Risk profile
- Technical risk: medium
- Blast radius: medium
- Failure modes:
  - Circular imports between the new ops module, codec, and existing callers if the split is done mechanically.
  - Public-surface drift if `migrations.py` forgets to re-export something tests do not cover.
  - Human-review-worthy churn if import moves accidentally alter package-root behavior.

## Best when
- We want a real boundary improvement now, not just a tidier file.
- We expect more migration scheduling and manifest logic to grow soon.
