# Phase 2: Extract Manifest Ops

## Scope
- `src/continuous_refactoring/migrations.py`
- `src/continuous_refactoring/migration_manifest_ops.py`
- `tests/test_migrations.py`
- Adjacent files only if required to keep imports or tests coherent:
  `src/continuous_refactoring/migration_manifest_codec.py`

required_effort: medium
effort_reason: module extraction has real import-cycle and compatibility risk

## Precondition
Phase 1 is complete, and the compatibility export contract plus behavior-locking
tests for `continuous_refactoring.migrations` are in place.

## Instructions
- Introduce `src/continuous_refactoring/migration_manifest_ops.py` as the new
  internal home for manifest operational helpers.
- Move operational logic there first:
  phase lookup helpers, current-phase resolution, cursor advancement, phase
  completion state updates, and wake-up eligibility helpers.
- Keep `MigrationManifest`, `PhaseSpec`, status vocabulary, path helpers, and
  the public `load_manifest()` / `save_manifest()` facade anchored in
  `migrations.py`.
- Preserve behavior exactly. This phase is about ownership and locality, not
  semantic change.
- Avoid speculative interfaces. One concrete internal module is enough.
- Do not redirect downstream callers yet unless a minimal import adjustment is
  required to keep the extraction coherent.

## Definition of Done
- `migration_manifest_ops.py` exists and owns the extracted manifest
  operational logic.
- `continuous_refactoring.migrations` still exports the locked compatibility
  symbol set from Phase 1.
- `load_manifest()` and `save_manifest()` still present the same public
  contract, with persistence and codec boundary behavior unchanged.
- The split does not introduce circular imports or duplicate, drifting copies
  of the same logic.
- The configured broad validation command passes.

## Validation
- Run `uv run pytest tests/test_migrations.py`.
- Run focused downstream checks that exercise imported helpers, expected to
  include `uv run pytest tests/test_phases.py tests/test_planning.py
  tests/test_prompts.py tests/test_wake_up.py`.
- Finish with `uv run pytest`.
