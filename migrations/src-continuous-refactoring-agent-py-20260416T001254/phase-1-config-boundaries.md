# Phase 1 — Move CLI-owned boundary logic into `config.py`

## Scope
`src/continuous_refactoring/config.py` only.

## Objective
Extract taste and migration-directory helper logic into `config.py` so `cli.py` becomes orchestration-only at the boundary.

## Instructions
1. Add boundary helpers in `config.py`: `resolve_taste_path(global_: bool, repo_root: Path | None = None) -> Path`, `resolve_taste_settle_path(taste_path: Path) -> Path`, and `normalize_live_migrations_dir(project_root: Path, live_migrations_dir: Path | str) -> Path`.
2. Ensure these helpers raise `ContinuousRefactorError` directly; no `SystemExit` or CLI messaging.
3. Export the new helpers in `__all__`.
4. Use them nowhere else outside config boundary yet; keep existing behavior in `cli.py` untouched for now.

## Readiness gates (machine-checkable)
1. Scope guard:
```bash
python - <<'PY'
import subprocess
import sys

changed = {line.strip() for line in subprocess.check_output(["git", "diff", "HEAD", "--", "src/continuous_refactoring"], text=True).splitlines()}
bad = [p for p in changed if p not in {"src/continuous_refactoring/config.py"} and p.endswith(".py")]
if bad:
    print("out-of-scope for phase 1:", ", ".join(sorted(bad)))
    sys.exit(1)
print("scope ok")
PY
```
2. New helper functions exist and are importable:
```bash
python - <<'PY'
from continuous_refactoring.config import (
    normalize_live_migrations_dir,
    resolve_taste_path,
    resolve_taste_settle_path,
)

assert callable(resolve_taste_path)
assert callable(resolve_taste_settle_path)
assert callable(normalize_live_migrations_dir)
print("helpers importable")
PY
```
3. Determinism and property checks:
```bash
python - <<'PY'
import random
import tempfile
from pathlib import Path

from continuous_refactoring.config import (
    global_dir,
    resolve_taste_path,
    resolve_taste_settle_path,
    normalize_live_migrations_dir,
)

random.seed(20260416)
with tempfile.TemporaryDirectory() as tmpdir:
    root = Path(tmpdir)
    for _ in range(200):
        rel = f"d{i}" if (i := random.randrange(1_000_000)) else "live"
        p = normalize_live_migrations_dir(root, Path(rel))
        if p is None:
            raise SystemExit("normalize returned None")
        assert p.is_relative_to(root)
        assert p == normalize_live_migrations_dir(root, rel)

    taste_path = root / "taste.md"
    assert resolve_taste_path(global_=True, repo_root=root).parent == (global_dir())
    settle_a = resolve_taste_settle_path(taste_path)
    settle_b = resolve_taste_settle_path(taste_path)
    assert settle_a == settle_b
    assert str(settle_a) == str((root / "taste.md.done").resolve())
    assert settle_a.name.endswith(".done")

print("property checks ok")
PY
```
4. Error mapping at boundary remains pure: `normalize_live_migrations_dir(root, Path("../outside"))` raises `ContinuousRefactorError` and no `SystemExit`.
5. Baseline for parser/input behavior is unchanged: run targeted tests before the next phase.

## Validation
1. Config-focused tests:
```bash
pytest -q tests/test_continuous_refactoring.py::test_package_exports_are_stable
```
2. CLI-facing command behavior from this phase is not yet shifted; keep `tests/test_taste*` smoke checks green.
3. Verify no new imports or helper logic were added to `cli.py` in this phase by ensuring changed files check above remains strict.

## Independent shippability
If anything regresses in `cli.py`, this phase can be paused and reverted without runtime behavior changes; it only adds reusable boundary helpers.
