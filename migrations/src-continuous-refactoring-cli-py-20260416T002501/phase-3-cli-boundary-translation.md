# Phase 3 — CLI single loop-adapter boundary

## Scope
- `src/continuous_refactoring/cli.py`
- `src/continuous_refactoring/__main__.py`
- `src/continuous_refactoring/__init__.py` (if exporting new boundary symbols)

## Objective
Make `cli.py` the sole process boundary for command translation: handlers raise domain errors, `_run_with_loop_errors` performs loop result/exception translation, and no handler performs direct `SystemExit` control-flow exits.

## Instructions
1. Add a CLI boundary exception in `cli.py`, e.g. `CliBoundaryError`, with `status` and `exit_code` (default `1`).
2. Replace handler-local `raise SystemExit(...)` uses for validation/business failures with `raise CliBoundaryError(...)`.
3. Keep parser/argparse-generated exits untouched (`argparse` behavior remains).
4. Implement `_run_with_loop_errors` as the only place that:
   - invokes loop command callables (`run_once`, `run_loop`);
   - translates `LoopExecutionError` and `ContinuousRefactorError` to stable process exit codes via `.exit_code`;
   - preserves interrupt path by allowing `130` to pass through.
5. Move all loop-call invocations so they go through `_run_with_loop_errors` and nowhere else.
6. In `cli_main`, wrap handler invocation with a single `CliBoundaryError` catch/exit path and keep parser `help`/`error` flows.
7. Update `__main__.py` to keep this single exit boundary as the external process-facing entrypoint.

## Ready_when (mechanical)
1. No CLI-local `SystemExit` raise statements remain:
```bash
python - <<'PY'
from pathlib import Path
text = Path('src/continuous_refactoring/cli.py').read_text(encoding='utf-8')
assert 'raise SystemExit(' not in text
print('cli has no handler-level SystemExit raises')
PY
```
2. `_run_with_loop_errors` exists and is the only loop-call translation point in `cli.py`:
```bash
python - <<'PY'
import ast
from pathlib import Path

tree = ast.parse(Path("src/continuous_refactoring/cli.py").read_text(encoding="utf-8"))

def fn_by_name(name):
    return next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name), None)

adapter = fn_by_name("_run_with_loop_errors")
if adapter is None:
    raise SystemExit("_run_with_loop_errors missing")

loop_callers = set()

parent = {}
stack = [tree]
while stack:
    node = stack.pop()
    for child in ast.iter_child_nodes(node):
        parent[id(child)] = node
        stack.append(child)

def enclosing_func(node):
    cur = parent.get(id(node))
    while cur is not None:
        if isinstance(cur, ast.FunctionDef):
            return cur.name
        cur = parent.get(id(cur))
    return None

def is_loop_call(node):
    if not isinstance(node, ast.Call):
        return False
    fn = node.func
    return (
        (isinstance(fn, ast.Name) and fn.id in {"run_once", "run_loop"})
        or (isinstance(fn, ast.Attribute) and fn.attr in {"run_once", "run_loop"})
    )

for n in ast.walk(tree):
    if is_loop_call(n):
        loop_callers.add(enclosing_func(n))

bad = {name for name in loop_callers if name != "_run_with_loop_errors"}
if bad:
    raise SystemExit(f"loop commands invoked outside adapter: {sorted(bad)}")
if "_run_with_loop_errors" not in loop_callers:
    raise SystemExit("adapter not used for loop calls")
print("single loop adapter boundary verified")
PY
```
3. CLI entrypoint owns loop translation:
```bash
python - <<'PY'
from pathlib import Path
import ast

text = Path("src/continuous_refactoring/cli.py").read_text(encoding="utf-8")
tree = ast.parse(text)
main = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "cli_main")
has_boundary_catch = any(
    isinstance(n, ast.ExceptHandler) and n.type
    and isinstance(n.type, ast.Name) and n.type.id == "CliBoundaryError"
    for n in ast.walk(main)
)
if not has_boundary_catch:
    raise SystemExit("cli_main does not catch CliBoundaryError")
print("cli_main translation ownership verified")
PY
```
4. Scope guard:
```bash
python - <<'PY'
import subprocess
allowed = {
    "src/continuous_refactoring/cli.py",
    "src/continuous_refactoring/__main__.py",
    "src/continuous_refactoring/__init__.py",
}
changed = {
    line.strip()
    for line in subprocess.check_output(
        ["git", "diff", "--name-only", "HEAD", "--", "src/continuous_refactoring"],
        text=True,
    ).splitlines()
}
bad = sorted(path for path in changed if path not in allowed and path.endswith(".py"))
if bad:
    raise SystemExit(f"out-of-scope edits: {bad}")
print("scope ok")
PY
```

## Validation
```bash
python -m py_compile \
  src/continuous_refactoring/cli.py \
  src/continuous_refactoring/__main__.py \
  src/continuous_refactoring/__init__.py

python - <<'PY'
from continuous_refactoring import cli
print("cli_main callable", callable(cli.cli_main))
PY
```

## Independent shippability
CLI process translation is centralized and only boundary-specific behavior changes here; loop entrypoints and core orchestration stay in their current execution contract.
