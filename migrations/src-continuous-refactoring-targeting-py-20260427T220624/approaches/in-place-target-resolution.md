# In-Place Targeting Resolution Tightening

## Strategy

Keep `src/continuous_refactoring/targeting.py` as the ownership point for all target semantics, but tighten the module into explicit, small pipeline helpers.

Core move:
- Move CLI-facing target parsing to a first-class helper in `targeting.py`:
  - `parse_paths_arg(raw: str | None) -> tuple[str, ...] | None`
  - validate/truncate-empty in one place, not ad hoc in `loop.py`.
- Introduce a tiny selector abstraction in `targeting.py`:
  - `select_target_files(patterns: tuple[str, ...], repo_root: Path) -> tuple[str, ...]`
  - `resolve_target_sources(...) -> tuple[list[Target], list[str]]` is still not a second data structure, just returns an ordered `list[Target]`.
- Keep `loop.py` orchestration thin:
  - `_resolve_targets_from_args()` delegates parsing and resolution; it only passes parser outputs.
- Preserve existing output contracts:
  - fallback provenance strings (`targets`, `globs`, `extensions`, `paths`, `random`),
  - random fallback behavior and warning text patterns,
  - `Target` dataclass shape and public imports.
- Normalize warnings/errors at module boundaries:
  - keep current behavior (`ContinuousRefactorError` on fatal git enumeration failures),
  - attach `__cause__` where wrapping adds context.

## Tradeoffs

Pros:
- Lowest churn across `loop.py`, `scope_expansion.py`, and tests.
- No module boundary churn, no migration of symbol ownership.
- Fastest path to measurable cleanup and easy review.

Cons:
- Retains a broader `targeting.py` surface than a full split.
- Less architectural separation than module extraction options.
- Any later boundary extraction will be easier from this cleaner baseline, not zero-cost.

## Estimated Phases

1. Baseline lock
- Add regression tests for `_parse_paths_arg` behavior and edge-case warnings in `tests/test_targeting.py`.
- Add one small `run-loop` integration assertion proving `loop.py` delegates to new parser behavior.

2. Internal pipeline cleanup
- Extract parsing and selection helpers inside `targeting.py`.
- Update `_resolve_targets_from_args()` in `loop.py` to call the new helper functions.
- Keep prompt composition unchanged; only target resolution shape changes through same contract.

3. Error-boundary hardening
- Wrap failed git enumeration paths with nested `ContinuousRefactorError`.
- Preserve user-facing strings where tests assert them; update only if intentional and justified.

4. Validation
- `uv run pytest tests/test_targeting.py tests/test_run_once_regression.py tests/test_prompts.py`
- Then focused `uv run pytest tests/test_cli_*.py` for any touched CLI path.

## Risk Profile

Low to medium.

Watch-outs:
- Keep warning wording stable to avoid brittle regression in stderr-capture tests.
- Keep first-match targeting semantics intact (`targets > globs > extensions > paths > random`).
- No new temporary flags, names, or compatibility indirection.

