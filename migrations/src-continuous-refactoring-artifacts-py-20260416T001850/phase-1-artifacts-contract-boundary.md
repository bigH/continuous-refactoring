# Phase 1 — Artifacts contract boundary hardening (`artifacts.py`)

## Scope
`src/continuous_refactoring/artifacts.py` only.

## Objective
Tighten artifact persistence contracts at module boundary while preserving all public behavior.

## Instructions
1. Add canonical module-level constants in `artifacts.py` for:
   - attempt keys
   - count keys
   - event field keys
   - terminal statuses
2. Add a private summary payload builder used by every write path.
3. Add a private atomic JSON writer and route all file writes through it.
4. Ensure status finalization passes through a module-owned normalization helper.
5. Keep public API signatures and exception class names unchanged.
6. Keep timestamp source and deterministic ordering behavior unchanged.
7. Avoid adding translation outside module boundaries; preserve original exception signals unless crossing boundary.

## Ready when (machine-checkable)
1. Scope guard:
```bash
python - <<'PY'
import subprocess

allowed = {"src/continuous_refactoring/artifacts.py"}
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
2. Canonical contract access check:
```bash
python - <<'PY'
import json
from pathlib import Path
from continuous_refactoring.artifacts import create_run_artifacts

artifacts = create_run_artifacts(Path.cwd(), agent="codex", model="m", effort="medium", test_command="true")
payload = json.loads(artifacts.summary_path.read_text(encoding="utf-8"))
expected = {"agent", "model", "effort", "attempts", "counts", "events", "final_status", "started_at", "updated_at", "test_command"}
assert expected.issubset(payload.keys())
from continuous_refactoring import artifacts as artifacts_mod
assert "completed" in artifacts_mod.TERMINAL_STATUSES
print("contract check passed")
PY
```
3. Deterministic attempt progression check:
```bash
python - <<'PY'
from pathlib import Path
import json
from continuous_refactoring.artifacts import create_run_artifacts

artifacts = create_run_artifacts(Path.cwd(), agent="codex", model="m", effort="medium", test_command="true")
artifacts.mark_attempt_started(1)
artifacts.mark_attempt_started(2)
summary = json.loads(artifacts.summary_path.read_text(encoding="utf-8"))
attempts = [a["attempt"] for a in summary["attempts"]]
assert attempts == [1, 2], attempts
print("attempt progression check passed")
PY
```

## Validation
1. Artifact-specific behavior tests:
```bash
pytest -q tests/test_continuous_refactoring.py::test_attempt_dir_rejects_retry_below_one
pytest -q tests/test_continuous_refactoring.py::test_default_artifacts_root_prefers_tmpdir
pytest -q tests/test_continuous_refactoring.py::test_default_artifacts_root_falls_back_to_tempdir
pytest -q tests/test_continuous_refactoring.py::test_create_run_artifacts_uses_single_timestamp
```
2. Compile gate:
```bash
python -m py_compile src/continuous_refactoring/artifacts.py
```

## Independent shippability
If phase 1 passes, the module contract is tightened and the repository remains shippable with unchanged external semantics.
