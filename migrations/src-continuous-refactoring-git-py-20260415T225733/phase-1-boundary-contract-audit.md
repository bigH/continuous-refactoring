# Phase 1: boundary-contract-audit

## Objective

Create a machine-checkable boundary map for the migration cluster before any source edits.

## Scope

- Read-only inspection of:
  - `src/continuous_refactoring/git.py`
  - `src/continuous_refactoring/loop.py`
  - `src/continuous_refactoring/phases.py`
  - `src/continuous_refactoring/config.py`
  - `src/continuous_refactoring/targeting.py`
  - `src/continuous_refactoring/__init__.py`
  - `src/continuous_refactoring/artifacts.py`
  - `src/continuous_refactoring/prompts.py`

## Deliverable

Create: `migrations/src-continuous-refactoring-git-py-20260415T225733/phase-1-boundary-contract-audit-notes.json`

## Artifact schema

```json
{
  "module": "git|loop|phases|config|targeting|__init__|artifacts|prompts",
  "module_role": "leaf-boundary|orchestration-boundary|package-export|pass-through-template",
  "edge_count": 0,
  "boundary_edges": [
    {
      "edge_id": "module:symbol[:line]",
      "source_module": "git",
      "source_symbol": "run_command",
      "caught_in_module": "git",
      "raised_type": "ContinuousRefactorError",
      "raised_message": "string summary",
      "is_wrapped": true,
      "cause_preserved": true,
      "owner_boundary": "git",
      "notes": "why this boundary owns the failure"
    }
  ]
}
```

### Required entries

- One top-level object per module in scope with at least:
  - `module`
  - `module_role`
  - `edge_count`
  - `boundary_edges`
- `edge_count` must be `0` only when `module_role` is `pass-through-template` or `package-export`.

## Instructions

1. Scan for all `ContinuousRefactorError` creation points, caught-exception translation points, and subprocess/file I/O boundary points.
2. Classify each edge owner by boundary:
   - `git.py` command/subprocess boundary
   - `config.py` config/persistence boundary
   - `loop.py` and `phases.py` orchestration boundary
   - `targeting.py` path/listing boundary
3. Keep `_init__` and `prompts.py` edges as pass-through/no-boundary unless evidence shows translation is added in later phases.
4. Explicitly list duplicate or intermediary translations that should be removed in later phases.
5. Preserve exact line references and import context for each edge for deterministic re-checks.

## Ready_when (machine-checkable)

1. Artifact exists at path:
   - `migrations/src-continuous-refactoring-git-py-20260415T225733/phase-1-boundary-contract-audit-notes.json`
2. `python` script validates schema and coverage:

```bash
python - <<'PY'
from pathlib import Path
import json

artifact_path = Path('migrations/src-continuous-refactoring-git-py-20260415T225733/phase-1-boundary-contract-audit-notes.json')
required_modules = {
    'git.py',
    'loop.py',
    'phases.py',
    'config.py',
    'targeting.py',
    'artifacts.py',
    '__init__.py',
    'prompts.py',
}
allow_non_edge_roles = {'pass-through-template', 'package-export'}

data = json.loads(artifact_path.read_text(encoding='utf-8'))
assert isinstance(data, list), 'artifact must be an array'

seen = {entry['module'] for entry in data if isinstance(entry, dict) and 'module' in entry}
assert seen == required_modules, f'missing modules: {sorted(required_modules - seen)}'

for entry in data:
    for key in [
        'module', 'module_role', 'edge_count', 'boundary_edges',
    ]:
        assert key in entry, f'{entry.get("module")}: missing key {key}'
    assert isinstance(entry['edge_count'], int) and entry['edge_count'] >= 0
    assert isinstance(entry['boundary_edges'], list)
    if entry['edge_count'] == 0:
        assert entry['module_role'] in allow_non_edge_roles
        continue
    for edge in entry['boundary_edges']:
        for key in [
            'edge_id', 'source_module', 'source_symbol', 'caught_in_module',
            'raised_type', 'raised_message', 'is_wrapped', 'cause_preserved',
            'owner_boundary', 'notes',
        ]:
            assert key in edge
        assert isinstance(edge['is_wrapped'], bool)
        assert isinstance(edge['cause_preserved'], bool)
        if edge['is_wrapped']:
            assert edge['raised_type'] == 'ContinuousRefactorError'
PY
```

3. `git diff --name-only` shows only files inside migration docs for this phase (no source edits in phase 1).

## Validation

1. `uv run pytest tests/test_git_branching.py::test_prepare_run_branch_reuses_existing_branch`
2. `uv run pytest tests/test_config.py::test_load_manifest_empty`
3. `uv run pytest tests/test_loop_migration_tick.py::test_eligible_ready_migration_advances_phase`
4. `uv run pytest tests/test_phases.py::test_ready_unverifiable_sets_awaiting_human_review`
5. `uv run pytest tests/test_targeting.py::test_load_targets_jsonl_skips_invalid`

## Exit criteria

- Artifact schema is complete and deterministic.
- Module-level pass-through roles are explicit (no fabricated edges).
- No source files in `src/continuous_refactoring/*` are changed in this phase.
