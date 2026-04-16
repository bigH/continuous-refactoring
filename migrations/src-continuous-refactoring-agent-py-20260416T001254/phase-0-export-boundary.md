# Phase 0 — Export boundary hardening (`__init__.py`)

## Scope
`src/continuous_refactoring/__init__.py` only.

## Objective
Make package exports deterministic and explicit while preserving existing public surface.

## Instructions
1. Replace `_exported_modules` and the deduplication loop with a static module export map.
2. Keep module re-exports available for compatibility (`continuous_refactoring.cli`, etc.).
3. Keep `__all__` as a deterministic tuple, built from explicit module export tuples.
4. Keep behavior same from importer perspective:
4. Keep behavior same from importer perspective: existing names from package exports remain importable and duplicate export failure is preserved as a hard failure.

## Readiness gates (machine-checkable)
1. Scope guard:
```bash
python - <<'PY'
import subprocess
import sys

changed = {line.strip() for line in subprocess.check_output(["git", "diff", "HEAD", "--", "src/continuous_refactoring"], text=True).splitlines()}
bad = [p for p in changed if p not in {"src/continuous_refactoring/__init__.py"} and p.endswith(".py")]
if bad:
    print("out-of-scope for phase 0:", ", ".join(sorted(bad)))
    sys.exit(1)
print("scope ok")
PY
```
2. Dynamic loop and bookkeeping names are removed:
`rg "_exported_modules|_seen_exports|for _module in" src/continuous_refactoring/__init__.py` returns no lines.
3. `__all__` is a static tuple in module scope and is sorted and complete against baseline:
```bash
python - <<'PY'
import json
import continuous_refactoring
from pathlib import Path

current = tuple(sorted(continuous_refactoring.__all__))
baseline = tuple(sorted(json.loads(Path("migrations/src-continuous-refactoring-agent-py-20260416T001254/phase-0-baseline.json").read_text(encoding="utf-8"))["exports"]))
if current != baseline:
    raise SystemExit(f"exports changed: {set(current) ^ set(baseline)}")
print("exports parity ok")
PY
```
4. Module imports stay shallow and explicit:
`python -m py_compile src/continuous_refactoring/__init__.py` exits 0.

## Validation
1. Import smoke:
```bash
python - <<'PY'
import continuous_refactoring

for name in (
    "cli_main",
    "parse_max_attempts",
    "run_loop",
    "run_once",
    "MigrationManifest",
    "PhaseSpec",
    "compose_full_prompt",
    "ContinuousRefactorError",
):
    assert hasattr(continuous_refactoring, name), name
print("exports smoke ok")
PY
```
2. Duplicate-export parity:
`python - <<'PY'; import continuous_refactoring; n=list(continuous_refactoring.__all__); assert len(n)==len(set(n)); print(len(n)); PY`

## Independent shippability
This phase only changes package export wiring and does not alter runtime command flow.
