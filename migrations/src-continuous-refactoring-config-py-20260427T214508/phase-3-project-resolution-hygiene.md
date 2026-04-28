# Phase 3: Project entry and path-resolution helpers

## Objective
Simplify entry parsing and path resolution inside `config.py` with explicit helpers so behavior is testable and less branchy.

## Scope
- `src/continuous_refactoring/config.py`
- `tests/test_config.py`

## Instructions
1. Replace nested or closure-style field parsing in `_entry_from_dict()` with explicit private helpers:
   - `_require_string_field()`
   - `_optional_string_field()`
   - `_entry_from_mapping(uid: str, data: Mapping[str, object])`
2. Add a private `_project_path_matches()` helper used only by `find_project()` and keep comparison logic in one place.
3. Refactor `find_project()` so path matching normalizes both input path and stored path before comparison.
4. Keep `set_live_migrations_dir()` behavior stable; only route through the helper to reduce branch duplication.
5. Add or update tests in `tests/test_config.py` for any changed `ContinuousRefactorError` messages caused by the new helpers.

## Precondition
- Phase 2 is complete in migration status.
- `src/continuous_refactoring/config.py` has no behavioral edits outside functions listed in this phase.
- No edits are present in `src/continuous_refactoring/cli.py`, `src/continuous_refactoring/loop.py`, `src/continuous_refactoring/prompts.py`, `src/continuous_refactoring/agent.py`, `src/continuous_refactoring/artifacts.py`, `src/continuous_refactoring/git.py` at phase start.

## Definition of Done
- Project-entry validation uses explicit helper functions with unchanged behavior for valid payloads and error type/value expectations for invalid payloads.
- `find_project()` path checks are explicit and stable for equivalent path forms.
- `set_live_migrations_dir()` still accepts valid inputs and rejects unknown project IDs exactly as before.
- All touched `tests/test_config.py` cases pass.
- `tests/test_config.py` still passes in full.

## Validation steps
- `uv run pytest tests/test_config.py::test_load_manifest_rejects_non_mapping_project_entry`
- `uv run pytest tests/test_config.py::test_register_project_detects_git_remote`
- `uv run pytest tests/test_config.py::test_resolve_live_migrations_dir_valid`
- `uv run pytest tests/test_config.py::test_resolve_live_migrations_dir_rejects_escape`
- `uv run pytest tests/test_config.py`
