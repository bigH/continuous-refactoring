# Phase 2: leaf-boundary-hardening-git-config

## Objective

Harden low-level failure translation in `git.py` and `config.py`, preserving root causes where boundaries translate exceptions.

## Scope

- `src/continuous_refactoring/git.py`
- `src/continuous_refactoring/config.py`

Out of scope:
- `loop.py`, `phases.py`, `targeting.py`, `__init__.py`, `prompts.py`

## Instructions

1. In `git.py`:
   1. Wrap `subprocess.run(...)` in `run_command` with explicit `except (OSError, subprocess.SubprocessError)` and re-raise `ContinuousRefactorError` using `from error`.
   2. Keep command execution success/failure semantics unchanged for `check=False` callers.
   3. Keep existing error strings and status semantics unchanged where not required.
2. In `config.py`:
   1. In `_load_manifest_payload`, preserve existing parse/shape errors but add explicit `from error` when raising on `read_text` failure or `json.JSONDecodeError`.
   2. In `save_manifest`, replace broad exception handling with narrower, explicit exception handling and explicit `from error` on failure paths where possible.
   3. Preserve existing behavior of `load_config_version`, `register_project`, `resolve_project`, and directory helpers.
3. Do not introduce feature flags/canaries.

## Ready_when (machine-checkable)

1. Every `raise ContinuousRefactorError` created inside an `except` in `git.py` or `config.py` has explicit `cause` (`from <error>`).
2. `git.py` and `config.py` do not introduce new third-party or local imports (import graph delta must be empty in this phase).

```bash
python - <<'PY'
import ast
import subprocess
from pathlib import Path


def iter_nodes_with_parent(tree: ast.AST):
    parent = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node
    return parent


for rel in ('src/continuous_refactoring/git.py', 'src/continuous_refactoring/config.py'):
    path = Path(rel)
    text = path.read_text(encoding='utf-8')
    tree = ast.parse(text)
    parent = iter_nodes_with_parent(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise):
            continue
        if not isinstance(node.exc, ast.Call):
            continue
        func = node.exc.func
        if not (isinstance(func, ast.Name) and func.id == 'ContinuousRefactorError'):
            continue
        p = parent.get(node)
        while p is not None and not isinstance(p, ast.ExceptHandler):
            p = parent.get(p)
        if p is None:
            continue
        assert node.cause is not None, f'{path}: raise without cause inside except at line {node.lineno}'

    before = subprocess.check_output(['git', 'show', f'HEAD:{rel}'], text=True)
    after_tree = tree
    before_tree = ast.parse(before)
    def import_set(t: ast.AST) -> set[tuple]:
        out: set[tuple] = set()
        for n in ast.walk(t):
            if isinstance(n, ast.Import):
                out.add(('import', tuple(sorted(alias.name for alias in n.names))))
            elif isinstance(n, ast.ImportFrom) and n.module:
                out.add(('from', n.module, tuple(sorted(alias.name for alias in n.names))))
        return out

    # allow no import additions/removals in phase 2 for deterministic rollout
    assert import_set(before_tree) == import_set(after_tree), f'{rel}: import set changed unexpectedly in phase 2'

print('ok')
PY
```

2. `git diff --name-only -- src/continuous_refactoring/git.py src/continuous_refactoring/config.py` includes only these files plus phase docs.
## Validation

1. `uv run pytest tests/test_config.py::test_load_manifest_rejects_non_object_payload`
2. `uv run pytest tests/test_config.py::test_load_manifest_rejects_non_mapping_projects`
3. `uv run pytest tests/test_config.py::test_save_and_load_manifest_roundtrip`
4. `uv run pytest tests/test_git_branching.py::test_run_observed_command_timeout`

## Exit criteria

- Exception translation in `git.py` and `config.py` is explicit and cause-preserving.
- No unrelated source files changed.
