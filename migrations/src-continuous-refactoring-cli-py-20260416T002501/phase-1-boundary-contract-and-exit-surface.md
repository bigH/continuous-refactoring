# Phase 1 — Boundary contract and exit surface inventory

## Scope
- `src/continuous_refactoring/artifacts.py`
- `src/continuous_refactoring/loop.py`

## Objective
Define a typed domain error contract that captures final failure intent before CLI-level process translation, and remove process-exit behavior from `loop.py`.

## Instructions
1. Add a new boundary exception in `artifacts.py`.
   - Exported name: `LoopExecutionError`.
   - Base: `ContinuousRefactorError`.
   - Required constructor fields:
     - `message: str`
     - `status: str`
     - `exit_code: int = 1`
   - Preserve caller chain: when called from `except`, use `from`.
2. Ensure `loop.py` imports the new boundary exception and has no `SystemExit` raises in module body.
3. Record a one-source-of-truth mapping table (in this phase notes or inline helper) for terminal failure tags used by CLI:
   - `migration_failed`
   - `agent_failed`
   - `validation_failed`
   - `baseline_failed`
   - `max_consecutive_failures`
4. Do not change loop control flow in this phase; keep behavior untouched.
5. Leave a single path to return-to-CLI boundaries: `loop.py` returns status or raises domain exceptions only.

## Ready_when (mechanical)
1. Scope guard:
```bash
python - <<'PY'
import subprocess
allowed = {
    "src/continuous_refactoring/loop.py",
    "src/continuous_refactoring/artifacts.py",
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
2. Loop exception contract exists and is typed:
```bash
python - <<'PY'
from inspect import isclass, signature
from continuous_refactoring import artifacts

err_cls = artifacts.__dict__.get("LoopExecutionError")
if err_cls is None or not isclass(err_cls):
    raise SystemExit("missing artifacts.LoopExecutionError")

import continuous_refactoring.artifacts
assert issubclass(err_cls, continuous_refactoring.artifacts.ContinuousRefactorError)

params = signature(err_cls).parameters
assert "status" in params and "exit_code" in params and "message" in params
sample = err_cls("x", status="migration_failed")
assert sample.status == "migration_failed"
assert sample.exit_code == 1
print("loop contract verified")
PY
```
3. No loop-level process exits:
```bash
python - <<'PY'
from pathlib import Path
assert 'SystemExit(' not in Path('src/continuous_refactoring/loop.py').read_text(encoding='utf-8')
print("no SystemExit in loop.py")
PY
```
4. Loop imports and references the domain error:
```bash
python - <<'PY'
from pathlib import Path
text = Path('src/continuous_refactoring/loop.py').read_text(encoding='utf-8')
if 'LoopExecutionError' not in text:
    raise SystemExit('LoopExecutionError not wired into loop.py')
print('loop wired to LoopExecutionError')
PY
```

## Validation
```bash
python -m py_compile \
  src/continuous_refactoring/loop.py \
  src/continuous_refactoring/artifacts.py

python - <<'PY'
from inspect import isclass
from continuous_refactoring.artifacts import LoopExecutionError
from continuous_refactoring import loop
assert isclass(LoopExecutionError)
print("phase 1 validation pass", LoopExecutionError, loop.__name__)
PY
```

## Independent shippability
This phase only introduces a boundary contract and removes process-exit behavior from loop internals. Current CLI entrypoints can still run without behavior changes.
