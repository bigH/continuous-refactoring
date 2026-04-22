# In-Place Manifest Cleanup

## Strategy

Keep all behavior in `migrations.py`, but reorganize the module around explicit sections and clearer helper names:

- domain values
- path helpers
- phase cursor operations
- manifest payload decoding
- manifest persistence
- scheduling

Within that structure:
- rename generic `_require_*` helpers where a manifest-specific name improves readability
- collapse low-value helpers only if the callsite becomes clearer
- add a small pure `manifest_to_payload()` helper if it makes `save_manifest()` read like a boundary
- leave legacy compatibility in place

This approach treats the file as still appropriately sized for the project, but currently arranged in a way that makes the parser dominate the reader’s attention.

## Tradeoffs

Pros:
- Lowest churn and lowest import risk.
- No new module to name or export.
- Keeps every existing monkeypatch/import path stable.
- Useful if the team wants a small, safe cleanup before choosing a larger boundary.

Cons:
- Does not create a durable home for codec behavior.
- `migrations.py` remains a mixed module after completion.
- Future changes may re-grow the same parser/operation tangle.
- The readability gain is capped because all responsibilities still share one file.

## Estimated Phases

1. **Tighten tests around current behavior**
   - Add missing edge cases only where there is actual risk: malformed JSON, unknown current phase on save, and bad optional field types.
   - Avoid tests that lock in private helper names.

2. **Reorder and rename**
   - Move helper groups into a reader-friendly order.
   - Rename only when the new name carries more truth; do not churn every `_require_*` helper.
   - Keep comments near zero.

3. **Clarify boundary functions**
   - Make `load_manifest()` read as: read JSON, decode manifest.
   - Make `save_manifest()` read as: validate, encode payload, atomic replace.
   - Preserve exact JSON output.

4. **Run focused and full tests**
   - `uv run pytest tests/test_migrations.py tests/test_wake_up.py`
   - `uv run pytest`

## Risk Profile

Low. This is mostly mechanical structure and naming.

Main watch-outs:
- Avoid cosmetic churn that makes later extraction harder to review.
- Do not delete legacy `ready_when` or integer cursor support.
- Do not hide schema validation behind clever generic helpers.
- Keep `ContinuousRefactorError` messages useful enough for callers and tests.

## Best Fit

Choose this if the migration budget is tiny or if a larger split needs a warm-up commit. As the whole migration, it is probably too timid: the codec-boundary approach buys more clarity for only slightly more risk.
