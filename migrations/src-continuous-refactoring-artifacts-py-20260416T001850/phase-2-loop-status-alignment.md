# Phase 2 — Loop boundary alignment (`loop.py`)

## Scope
`src/continuous_refactoring/loop.py` only, with phase-1 `artifacts.py` already updated.

## Objective
Use canonical terminal status constants from `artifacts.py` and keep loop control unchanged.

## Instructions
1. Remove loop-local terminal status constants/strings that duplicate boundary vocabulary.
2. Import canonical terminal status constants from `continuous_refactoring.artifacts`.
3. Add a tiny helper for run-attempt refactor directory derivation that delegates to `artifacts.attempt_dir(...)/"refactor"`.
4. Add a local normalizer that maps final outcomes to `artifacts.TERMINAL_STATUSES` before calling `artifacts.finish(...)`.
5. Keep return codes, commit/push logic, and `artifacts.log(...)` payload keys unchanged.

## Ready when (machine-checkable)
1. Scope guard:
```bash
python - <<'PY'
import subprocess

allowed = {
    "src/continuous_refactoring/artifacts.py",
    "src/continuous_refactoring/loop.py",
}
changed = {
    line.strip()
    for line in subprocess.check_output(
        ["git", "diff", "--name-only", "HEAD", "--", "src/continuous_refactoring"],
        text=True,
    ).splitlines()
    if line.strip().endswith(".py")
}
extra = sorted(path for path in changed if path not in allowed)
if extra:
    raise SystemExit(f"out-of-scope edits: {extra}")
print("scope ok")
PY
```
2. Canonical terminal status ownership at module boundary:
```bash
python - <<'PY'
import ast
from pathlib import Path

tree = ast.parse(Path("src/continuous_refactoring/loop.py").read_text(encoding="utf-8"))
forbidden_literals = {
    "running",
    "completed",
    "failed",
    "interrupted",
    "migration_failed",
    "baseline_failed",
    "agent_failed",
    "validation_failed",
    "max_consecutive_failures",
}
found_assignments = set()
for node in ast.walk(tree):
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        target = node.targets[0] if isinstance(node, ast.Assign) else node.target
        if isinstance(target, ast.Name) and node.value.__class__ is ast.Constant and isinstance(node.value.value, str):
            if target.id in forbidden_literals or node.value.value in forbidden_literals:
                found_assignments.add(target.id)
if found_assignments:
    raise SystemExit(f"loop defines terminal status literals: {sorted(found_assignments)}")
print("boundary ownership check passed")
PY
```
3. Final status still maps only to canonical terminal set:
```bash
python - <<'PY'
from pathlib import Path
from continuous_refactoring.artifacts import create_run_artifacts

artifacts = create_run_artifacts(Path.cwd(), agent="codex", model="m", effort="medium", test_command="true")
artifacts.finish("completed")
assert artifacts.final_status in artifacts.TERMINAL_STATUSES
print("terminal constraint check passed")
PY
```

## Validation
1. Loop-flow tests:
```bash
pytest -q tests/test_run.py::test_run_creates_branch tests/test_run.py::test_run_exhausts_max_attempts_on_persistent_validation_failure tests/test_run.py::test_run_exhausts_max_attempts_on_persistent_agent_failure
pytest -q tests/test_run_once.py::test_run_once_creates_branch tests/test_run_once.py::test_run_once_no_fix_retry tests/test_run_once.py::test_run_once_timeout
pytest -q tests/test_loop_migration_tick.py::test_eligible_ready_migration_advances_phase tests/test_loop_migration_tick.py::test_no_eligible_migrations_falls_through
```
2. Interrupt and finalization behavior:
```bash
pytest -q tests/test_run.py::test_run_ctrl_c_discards_and_summarizes tests/test_run_once.py::test_ctrl_c_prints_file_paths
```
3. Compile gate:
```bash
python -m py_compile src/continuous_refactoring/loop.py
```

## Independent shippability
If phase 2 passes, this stays shippable: orchestration logic is unchanged and status ownership is now centralized in `artifacts.py`.
