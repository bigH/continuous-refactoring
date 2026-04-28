# Codec-Style Config Boundary + Stronger Error Contract

## Strategy

Introduce a dedicated config codec layer to separate pure data-structure conversion from process orchestration while preserving all caller-facing symbols in `config.py`.

Proposed flow:
- New `config_codec.py` owns raw JSON payload decoding/encoding for `manifest.json` payload and project-entry validation.
- `config.py` becomes a light caller-facing policy layer: file path orchestration, project lifecycle, taste resolution, and API composition.
- Boundary rule: codec raises raw `json`/`OSError` errors where useful internally, while `config.py` wraps as `ContinuousRefactorError` with preserved causes where crossing module boundaries.
- The approach mirrors `migrations` codec discipline and keeps runtime behavior stable.

## Tradeoffs

Pros:
- Clear split between data parsing and side-effectful orchestration, which is easier to reason about than large `config.py` methods.
- Better future-proofing for manifest version upgrades and schema expansion.
- Minimal callsite change: most imports stay in `config.py`.

Cons:
- New module overhead with extra plumbing and one extra layer in stack traces.
- The cleanest value appears only if we keep codec invariants strictly aligned with current payload shape.
- Requires tests in both `tests/test_config.py` and the new codec module.

## Estimated Phases

1. Codec extraction
   - Add `src/continuous_refactoring/config_codec.py` with payload decoder/encoder and validation helpers.
   - Move/duplicate current strict checks from `config._load_manifest_payload`, `_entry_from_dict`, and `load_manifest` into codec.

2. Boundary wiring
   - Refactor `config.py` to delegate payload transformation to codec and keep existing function names stable.
   - Keep `load_taste`/`default_taste_text` behavior unchanged on external outputs.

3. Error contract cleanup
   - Add focused tests for wrapped-vs-unwrapped failures in `tests/test_config.py`.
   - Ensure malformed JSON still fails fast and with actionable errors.

4. Validation and migration touchpoint sweep
   - Run config and CLI/taste tests, and a focused `loop` regression run for `resolve_project`/taste resolution paths.

## Risk Profile

Medium risk. Main risk is schema mismatch between codec and current callers that could alter edge-case behavior.

Watch-outs:
- Keep codec permissive enough only where tests prove legacy payload must remain accepted.
- Preserve stable exception types observed by callers where not already tested.
- Do not introduce a staged rollout; this is one migration in this repo.

