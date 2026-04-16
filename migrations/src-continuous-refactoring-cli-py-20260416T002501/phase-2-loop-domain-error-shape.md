# Phase 2 — Loop behavior stability under structured domain failures

## Scope
- `src/continuous_refactoring/loop.py`

## Objective
Make terminal failure exits in `run_once` and `run_loop` deterministic by converting each terminal branch to `LoopExecutionError` and preserving the final status tags introduced in phase 1.

## Instructions
1. Replace terminal `raise ContinuousRefactorError(...)` sites in `run_once`/`run_loop` with `LoopExecutionError`.
2. Preserve the cause chain:
   - `raise LoopExecutionError(... ) from error` in caught exception blocks.
   - Keep `except ContinuousRefactorError as error` handling where needed and rethrow with loop contract.
3. Keep `KeyboardInterrupt` behavior unchanged (`130`) and artifact path print in loop module.
4. Keep final-status intent stable and explicit:
   - `migration_failed`
   - `agent_failed`
   - `validation_failed`
   - `baseline_failed`
   - `max_consecutive_failures`
5. Keep cleanup safety:
   - `artifacts.finish(...)` must still execute in `finally` once per invocation.
6. Keep return codes from `run_once` and `run_loop` to `{0, 130}` for success/interrupt only.

## Ready_when (mechanical)
1. Phase 1 contract still active:
```bash
python - <<'PY'
from continuous_refactoring.artifacts import LoopExecutionError
from inspect import isclass
from continuous_refactoring import loop
assert isclass(LoopExecutionError)
assert hasattr(LoopExecutionError("x", status="x"), "status")
assert LoopExecutionError("x", status="x").exit_code == 1
assert not hasattr(loop, "LoopExecutionError") or loop.LoopExecutionError is LoopExecutionError
print("phase-1 contract is active")
PY
```
2. `run_once` and `run_loop` terminal raises must be loop-domain-only:
```bash
python - <<'PY'
import ast
from pathlib import Path

tree = ast.parse(Path("src/continuous_refactoring/loop.py").read_text(encoding="utf-8"))
fn_map = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
targets = ["run_once", "run_loop"]

for fn_name in targets:
    node = fn_map.get(fn_name)
    if node is None:
        raise SystemExit(f"missing function {fn_name}")

    bad_raises = 0
    unbounded_raises = 0
    for body_node in ast.walk(node):
        if not isinstance(body_node, ast.Raise):
            continue

        if body_node.exc is None:
            unbounded_raises += 1
            continue

        func = body_node.exc
        is_loop_err = isinstance(func, ast.Call) and isinstance(func.func, ast.Name) and func.func.id == "LoopExecutionError"
        is_direct_loop_err = isinstance(func, ast.Name) and func.id == "LoopExecutionError"
        is_call_loop_err_attr = (
            isinstance(func, ast.Call)
            and isinstance(func.func, ast.Attribute)
            and func.func.attr == "LoopExecutionError"
        )
        is_system_exit = (
            (isinstance(func, ast.Call)
             and isinstance(func.func, ast.Name)
             and func.func.id == "SystemExit")
            or (isinstance(func, ast.Name) and func.id == "SystemExit")
        )

        if is_system_exit:
            raise SystemExit(f"{fn_name} still raises SystemExit")
        if not (is_loop_err or is_direct_loop_err or is_call_loop_err_attr):
            bad_raises += 1

    if bad_raises:
        raise SystemExit(f"{fn_name} has {bad_raises} terminal raise that are not LoopExecutionError")
    if unbounded_raises > 1:
        raise SystemExit(f"{fn_name} has {unbounded_raises} bare raise statements; review for non-terminal flow")

    print(f"{fn_name} terminal raise check ok")
PY
```
3. Return semantics remain success/interrupt only from loop entrypoints:
```bash
python - <<'PY'
import ast
from pathlib import Path

tree = ast.parse(Path("src/continuous_refactoring/loop.py").read_text(encoding="utf-8"))

for fn_name in ("run_once", "run_loop"):
    fn = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == fn_name)
    const_returns = {
        n.value.value
        for n in ast.walk(fn)
        if isinstance(n, ast.Return)
        and isinstance(n.value, ast.Constant)
        and isinstance(n.value.value, int)
    }
    if not const_returns.issubset({0, 130}):
        raise SystemExit(f"{fn_name} has return ints outside {{0,130}}: {sorted(const_returns)}")
    if 0 not in const_returns:
        raise SystemExit(f"{fn_name} does not return success path 0")
    print(f"{fn_name} return-shape check ok: {sorted(const_returns)}")
PY
```
4. `artifacts.finish` is still guaranteed per run-loop entrypoint invocation:
```bash
python - <<'PY'
import ast
from pathlib import Path

tree = ast.parse(Path("src/continuous_refactoring/loop.py").read_text(encoding="utf-8"))
for fn_name in ("run_once", "run_loop"):
    fn = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == fn_name)
    finish_calls = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "finish"
    ]
    if len(finish_calls) != 1:
        raise SystemExit(f"{fn_name} expected exactly one artifacts.finish call in finally path, found {len(finish_calls)}")
    print(f"{fn_name} finish call count ok")
PY
```
5. Scope guard:
```bash
python - <<'PY'
import subprocess
changed = {
    line.strip()
    for line in subprocess.check_output(
        ["git", "diff", "--name-only", "HEAD", "--", "src/continuous_refactoring/loop.py"],
        text=True,
    ).splitlines()
}
if any(path != "src/continuous_refactoring/loop.py" for path in changed if path.endswith(".py")):
    raise SystemExit(f"out-of-scope edits in phase 2: {sorted(changed)}")
print("scope ok")
PY
```

## Validation
```bash
python -m py_compile src/continuous_refactoring/loop.py

python - <<'PY'
from continuous_refactoring.loop import run_once, run_loop
print("loop entrypoints importable:", callable(run_once), callable(run_loop))
PY

pytest -q tests/test_run_once.py tests/test_run.py
```

## Independent shippability
If this phase passes, loop entrypoints still preserve user-visible behavior and now provide strict, structured terminal failure signals for CLI translation.
