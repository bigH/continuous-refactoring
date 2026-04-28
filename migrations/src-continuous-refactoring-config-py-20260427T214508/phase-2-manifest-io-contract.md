# Phase 2: Manifest IO boundary contract

## Objective
Create a single, explicit read path in `config.py` where manifest I/O and decode failures are wrapped at the module boundary with nested causes.

## Scope
- `src/continuous_refactoring/config.py`
- `tests/test_config.py`

## Instructions
1. Add private helpers in `config.py` to isolate manifest payload acquisition:
   - `_read_manifest_text()`
   - `_parse_manifest_payload(text: str)`
   Keep `manifest_path()` as the only path-construction source.
2. Replace current in-function parsing/load handling so both `load_manifest()` and `load_config_version()` call the same wrapped payload pathway.
3. Keep `load_manifest()` returning `{}` when manifest does not exist.
4. Ensure `_load_manifest_payload()` raises `ContinuousRefactorError` for read and JSON decode failures, chaining the exact original exception in `__cause__`.
5. Keep public names and `__all__` unchanged.
6. Add/update tests in `tests/test_config.py` for:
   - malformed JSON raises `ContinuousRefactorError`,
   - file read failures raise `ContinuousRefactorError`,
   - successful parsing produces identical manifest values.

## Precondition
- Phase 1 is marked complete in the migration manifest.
- `uv run pytest tests/test_config.py` is green before edits.
- `src/continuous_refactoring/config.py` contains only production edits introduced in this phase.
- The public config API surface before this phase includes these names in `__all__`:  
  `find_project`, `load_config_version`, `load_manifest`, `load_taste`, `register_project`, `resolve_live_migrations_dir`, `resolve_project`.

## Definition of Done
- `_load_manifest_payload()` wraps read/parse failures as `ContinuousRefactorError` and preserves root cause on `__cause__`.
- `load_manifest()` and `load_config_version()` both consume the same manifest payload boundary contract.
- `load_manifest()` still returns `{}` for missing manifest files.
- All existing `tests/test_config.py` behavior assertions remain green and new boundary tests for malformed IO/cause behavior pass.
- `src/continuous_refactoring/config.py` keeps all public names unchanged.

## Definition of Done (gating checks)
- `uv run pytest tests/test_config.py`
- `rg -n "^def |^class " src/continuous_refactoring/config.py | sed -n '1,120p'` shows only intended helper additions in this phase.

## Validation steps
- `uv run pytest tests/test_config.py::test_load_manifest_empty`
- `uv run pytest tests/test_config.py::test_load_manifest_rejects_non_object_payload`
- `uv run pytest tests/test_config.py::test_load_manifest_rejects_non_mapping_projects`
- `uv run pytest tests/test_config.py`
