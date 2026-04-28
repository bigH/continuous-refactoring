# Phase 1: Manifest boundary baseline and regression lock

## Objective
Lock current manifest boundary behavior and encode failure-causality expectations before touching production logic in `config.py`.

## Scope
- `tests/test_config.py`

## Instructions
1. Add explicit tests in `tests/test_config.py` for malformed JSON payloads in `load_manifest` and `load_config_version`.
2. Add tests that verify `ContinuousRefactorError` is raised for manifest read/parse faults and that the original error object is preserved on `__cause__`.
3. Add a read-failure regression test that monkeypatches manifest read to raise `OSError` and asserts no silent fallback outside `load_manifest` missing-file semantics.
4. Keep all existing behavioral expectations intact for path resolution, project registration, and taste loading tests.
5. Do not edit production files in phase 1.

## Precondition
- `tests/test_config.py` currently passes.
- `src/continuous_refactoring/config.py` has no uncommitted edits in this branch.
- `tests/test_config.py` is the only file modified before this phase begins.

## Definition of Done
- New tests explicitly pin boundary failure behavior for malformed payloads and I/O failures.
- Existing `test_config.py` assertions still pass after adding new regression tests.
- No production source files are modified in this phase.
- Targeted regression tests are deterministic and do not depend on side effects outside temporary directories.

## Validation steps
- `uv run pytest tests/test_config.py`
