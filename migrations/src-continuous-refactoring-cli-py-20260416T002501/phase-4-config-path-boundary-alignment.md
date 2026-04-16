# Phase 4 — Config-backed path and context boundary alignment

## Scope
- `src/continuous_refactoring/config.py`
- `src/continuous_refactoring/cli.py`

## Objective
Shift path/project/review context resolution out of handler-local CLI branches and into domain-level config helpers, while keeping CLI ownership of user messaging and final exit translation.

## Instructions
1. Add explicit config helpers:
   - `resolve_taste_path(*, repo_root: Path, global_: bool) -> Path`
   - `resolve_review_context_path(*, repo_root: Path) -> Path`
   - `resolve_and_validate_project(*, repo_root: Path) -> ResolvedProject`
   - `resolve_and_validate_live_migrations_dir(*, repo_root: Path) -> Path`
2. Each helper must raise `ContinuousRefactorError` on boundary violations with meaningful messages; CLI will format final exit codes.
3. Migrate CLI helper callsites to these config entry points:
   - `_resolve_taste_path`
   - `_handle_init` live migration path checks/normalization
   - `_resolve_review_context`
4. Delete helper-level duplicate checks from handlers:
   - no direct `project` resolution + local message branching for project-not-registered in `_resolve_taste_path` and `_resolve_review_context`;
   - no inline absolute/relative validation for migration-dir path acceptance in `_handle_init`.
5. Keep user-facing strings for these flows stable:
   - `Error: project not initialized. Run 'continuous-refactoring init' first.`
   - `Error: no live-migrations-dir configured for this project.`
   - `Error: --live-migrations-dir must be inside the repo: ...`
6. Remove dead legacy branches once new helpers are adopted; avoid temporary compatibility layers.

## Ready_when (mechanical)
1. New config boundary helpers are present and importable:
```bash
python - <<'PY'
import ast
from pathlib import Path

tree = ast.parse(Path('src/continuous_refactoring/config.py').read_text(encoding='utf-8'))
required = {
    'resolve_taste_path',
    'resolve_review_context_path',
    'resolve_and_validate_project',
    'resolve_and_validate_live_migrations_dir',
}
found = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
missing = sorted(required - found)
if missing:
    raise SystemExit(f"missing config helpers: {missing}")
print("config helpers present")
PY
```
2. CLI no longer performs local project/path failure branching for taste/review context (AST-level delegation check):
```bash
python - <<'PY'
import ast
from pathlib import Path

cli_path = Path('src/continuous_refactoring/cli.py')
tree = ast.parse(cli_path.read_text(encoding='utf-8'))
lines = cli_path.read_text(encoding='utf-8').splitlines()

name_to_node = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}

def check_delegates(fn_name, required_call):
    node = name_to_node.get(fn_name)
    if node is None:
        raise SystemExit(f"missing function {fn_name}")

    source = "\n".join(lines[node.lineno - 1:node.end_lineno])
    if required_call not in source:
        raise SystemExit(f"{fn_name} must call {required_call}")

    banned = {"resolve_project", "resolve_live_migrations_dir", "global_dir", "is_relative_to"}
    for b in banned:
        if b in source:
            raise SystemExit(f"{fn_name} still contains local boundary logic ({b})")
    print(f"{fn_name} delegates to config helper")

for fn, helper in [
    ("_resolve_taste_path", "resolve_taste_path"),
    ("_resolve_review_context", "resolve_review_context_path"),
]:
    check_delegates(fn, helper)

handle_init = name_to_node.get("_handle_init")
if handle_init is None:
    raise SystemExit("missing _handle_init")
handle_init_src = "\n".join(lines[handle_init.lineno - 1:handle_init.end_lineno])
if "resolve_and_validate_live_migrations_dir" not in handle_init_src:
    raise SystemExit("missing _handle_init delegation to resolve_and_validate_live_migrations_dir")
if "is_relative_to(" in handle_init_src:
    raise SystemExit("_handle_init still performs local live migration path boundary checks")
for token in {"resolve_project", "resolve_live_migrations_dir", "global_dir"}:
    if token in handle_init_src:
        raise SystemExit(f"_handle_init still imports local boundary function {token}")
print("CLI handler delegation checks ok")
PY
```
3. Boundary contract still enforced:
```bash
python - <<'PY'
from pathlib import Path
text = Path('src/continuous_refactoring/cli.py').read_text(encoding='utf-8')
for token in ('_resolve_taste_path', '_resolve_review_context'):
    if token not in text:
        raise SystemExit(f"missing boundary entrypoints: {token}")
print("boundary entrypoints retained")
PY
```
4. Scope guard:
```bash
python - <<'PY'
import subprocess
allowed = {
    'src/continuous_refactoring/cli.py',
    'src/continuous_refactoring/config.py',
}
changed = {
    line.strip()
    for line in subprocess.check_output(
        ["git", "diff", "--name-only", "HEAD", "--", "src/continuous_refactoring"],
        text=True,
    ).splitlines()
}
bad = sorted(path for path in changed if path not in allowed and path.endswith('.py'))
if bad:
    raise SystemExit(f"out-of-scope edits: {bad}")
print('scope ok')
PY
```

## Validation
```bash
python -m py_compile \
  src/continuous_refactoring/config.py \
  src/continuous_refactoring/cli.py

python - <<'PY'
from continuous_refactoring import config, cli
print('config helpers importable')
print(config.resolve_review_context_path.__name__, config.resolve_taste_path.__name__)
print('cli delegations present')
print(hasattr(cli, "_resolve_taste_path"), hasattr(cli, "_resolve_review_context"))
PY
```

## Independent shippability
After this phase, domain-bound path and project checks are centralized in config; CLI remains a pure boundary translator and parser-facing command layer.
