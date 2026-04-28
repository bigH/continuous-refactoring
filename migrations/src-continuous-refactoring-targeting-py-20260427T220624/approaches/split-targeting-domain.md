# Split Targeting by Domain Ownership

## Strategy

Introduce explicit domain modules and keep `targeting.py` as a facade:
- `src/continuous_refactoring/targeting_io.py`
  - JSONL parsing/validation (`load_targets_jsonl`, `validate_target_line`)
  - `_optional_str` and field mapping (`effort-override`, `model-override`)
- `src/continuous_refactoring/targeting_match.py`
  - pattern compilation (`_compile_glob`)
  - `parse_extensions`, `parse_globs`, `expand_patterns_to_files`
- `src/continuous_refactoring/targeting_resolution.py`
  - `resolve_targets` policy and source precedence
- `src/continuous_refactoring/targeting.py`
  - stable façade, `Target`, `TargetSource`, `select_random_files`
  - re-exports and orchestration glue only.

This aligns with taste-scoping by making domain boundaries meaningful:
parsing, matching, and policy are separate and testable without CLI, agent, or loop context.

## Tradeoffs

Pros:
- Clearer code ownership and fewer long-distance responsibilities in one file.
- Easier targeted tests for each boundary (pure parsing/matching/resolution).
- Reduced pressure on `targeting.py` as behavior keeps growing.

Cons:
- Medium-high import churn (`loop.py`, tests, `__init__.py` surface, maybe `prompts.py` type imports).
- Higher chance of symbol/export conflict with package uniqueness checks.
- More files to keep in sync while maintaining deterministic behavior and warning wording.

## Estimated Phases

1. Test and contract capture
- Split existing tests into focused ownership buckets:
  - keep `tests/test_targeting.py` for top-level orchestration and cross-boundary behavior,
  - add `tests/test_targeting_match.py` for glob semantics,
  - add `tests/test_targeting_resolution.py` for precedence and fallback.

2. Extract parsing module
- Move validation and JSONL loading into `targeting_io.py`.
- Update direct imports where `validate_target_line` and `load_targets_jsonl` are used.

3. Extract matching module
- Move glob and extension parsing to `targeting_match.py`.
- Ensure dedupe/sort/range behavior stays identical; expand tests using existing randomized generator case.

4. Extract resolution module
- Move precedence/fallback policy into `targeting_resolution.py`.
- Keep return-order semantics stable and deterministic.

5. Facade and package integration
- Keep stable imports from `targeting.py` where external callers expect it.
- Update `src/continuous_refactoring/__init__.py` if new public symbols are intentionally exported.
- Final smoke tests.

## Risk Profile

Medium.

Watch-outs:
- Avoid speculative new API: no extra adapters, no temporary compatibility aliases.
- Do not rename the "truthy" precedence order; any change must be explicit and covered by tests.
- Ensure package-level uniqueness passes after each phase; no duplicate exports allowed.

