# Phase 3: Tidy Execution Pipeline

## Objective

Remove the incidental duplication exposed by Phase 2 and leave `phases.py` with crisp names, stable contracts, and no speculative structure.

This is a cleanup pass, not a second extraction migration.

## Precondition

Phase 2 is complete: `execute_phase()` has been extracted into private in-module helpers, public imports are unchanged, artifact paths are stable, and all Phase 2 validation commands pass.

## Scope

Allowed files:

- `src/continuous_refactoring/phases.py`
- `tests/test_phases.py`
- `src/continuous_refactoring/__init__.py` only if package export checks reveal a real issue
- `AGENTS.md` only if this migration changed a repo-contract statement

Do not introduce new modules. Do not move readiness code out of `phases.py`.

## Instructions

1. Remove duplicated failure handling introduced or exposed by the extraction.
   - Keep one clear path for terminal failure outcome creation.
   - Keep retryable validation failure handling explicit enough to audit rollback.
2. Rename weak locals only when the new name clarifies behavior.
   - `current_retry` may become a clearer attempt-budget name if tests still read cleanly.
   - Avoid vague names such as `result`, `data`, `temp`, or `info` when a domain name is available.
3. Keep comments near zero. If a comment is needed, it must explain a load-bearing behavior such as retry numbering or rollback timing.
4. Re-check `__all__` and package import behavior.
   - No new public symbols should be exported from `phases.py`.
   - `src/continuous_refactoring/__init__.py` should still import cleanly and reject duplicate public symbols.
5. Do not collapse helpers if they make the execution flow more readable. Single-call helpers are acceptable when they document a real phase step.
6. Do not broaden the migration into `prompts.py`, `migrations.py`, `planning.py`, `agent.py`, or `artifacts.py` unless a failing test proves the local refactor broke a contract there.

## Definition of Done

- `phases.py` remains the domain-focused owner of phase readiness and execution.
- `execute_phase()` and its helpers are readable without extra abstraction layers.
- No compatibility aliases, re-export shims, new modules, or runtime dependencies were added.
- Focused and full validation pass.
- `AGENTS.md` is still truthful for any contract touched by this migration.
- The repository is shippable after this phase.

## Validation

Run:

```sh
uv run pytest tests/test_phases.py
uv run pytest tests/test_continuous_refactoring.py tests/test_prompts.py
uv run pytest
```
