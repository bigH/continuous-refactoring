# Module-boundary tightening and import hygiene

## Strategy
- Make module boundaries explicit:
  - `cli.py` handles argument parsing and user-facing messages.
  - `config.py` handles persistent/config lookups.
  - `prompts.py` stays pure template assembly.
  - `agent.py` owns command execution + subprocess edge semantics.
- Stop relying on broad dynamic re-export from `__init__.py`; make exports explicit and minimal.
- Remove dead or ambiguous transitional names/paths in touched modules while keeping backward-compatible runtime behavior.

## Why this is useful
- Current `__init__.py` dynamically re-exports symbols from many modules and can make import-time dependency chains brittle.
- The flow in this cluster crosses boundaries for control/state/logging in several places; explicit boundaries reduce future churn risk.

## Tradeoffs
- Pros
  - Better readable imports and easier module navigation.
  - Lower risk of hidden import side effects in future refactors.
  - Clearer ownership of error translation and I/O boundaries.
- Cons
  - One-time churn in import style and potential lint/typing cleanup.
  - Slightly noisier diffs in files that currently rely on `from continuous_refactoring import *` semantics via package-level exports.

## Estimated phases
1. **Export cleanup (`__init__.py`)**
   - Replace `_exported_modules` looping with explicit `__all__` assembly from each module import list or static tuple.
   - Keep symbol compatibility stable by preserving existing exported names.
2. **CLI/config boundary cleanup**
   - Pull repeated taste-path/version parsing and project-resolution checks into concise, testable helpers in `config.py` and use them from `cli.py`.
   - Keep CLI functions responsible only for presenting errors and exit codes.
3. **Prompt and route flow alignment**
   - In `prompts.py` and `phases.py`, keep helpers pure and return normalized strings/ready verdicts only.
   - Remove low-value comments/docstrings that only restate code behavior.

## Risk profile
- Risk level: **Medium-Low**.
- Failure modes: import-time regressions, changed name resolution during module reloads, or subtle CLI behavior drift in error paths.
- Mitigation: preserve `__all__` contract, keep runtime-facing CLI messages identical unless explicitly improved, add quick smoke imports for all touched entrypoints.

## Migration footprint
- `src/continuous_refactoring/__init__.py`
- `src/continuous_refactoring/cli.py`
- `src/continuous_refactoring/config.py`
- `src/continuous_refactoring/prompts.py`
