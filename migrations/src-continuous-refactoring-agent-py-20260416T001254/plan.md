# Migration plan: module-boundary-tightening

## Migration target
- ID: `src-continuous-refactoring-agent-py-20260416T001254`
- Chosen approach: `approaches/module-boundary-tightening.md`
- Scope label candidate: `local-cluster`

## Chosen approach intent
Tighten module boundaries across:
- `__init__.py`
- `config.py`
- `cli.py`
- `prompts.py`
- `phases.py`

## Explicitly excluded
- `approaches/run-orchestration.md` is not in scope.
- `src/continuous_refactoring/agent.py` and `src/continuous_refactoring/loop.py` are read for dependency understanding only.
- No behavioral refactor of orchestration (`run_once`/`run_loop`) is included in this migration.

## Scope rules
Required editable files: `src/continuous_refactoring/__init__.py`, `src/continuous_refactoring/config.py`, `src/continuous_refactoring/cli.py`, `src/continuous_refactoring/prompts.py`, `src/continuous_refactoring/phases.py`.
- Files outside scope must never be modified in any phase.
- `migrations/src-continuous-refactoring-agent-py-20260416T001254/plan.md` and phase files may be updated for planning only.

## Taste constraints that drive validation
- Keep exception translation at module boundaries and preserve exception causes unless an actual boundary requires conversion.
- Keep comments low and avoid non-functional wrappers.
- Truthful names: avoid non-semantic temporary naming and weak migration names.
- Shipped-project safety: avoid risky behavior changes; migration should be boundary-focused.
- For pure, bounded behavior, use property-style checks instead of only example assertions.

## Dependency graph
- `phase-1-config-boundaries.md` depends on no earlier phase.
- `phase-2-cli-boundaries.md` depends on `phase-1`.
- `phase-3-pure-prompts-and-phases.md` depends on no earlier phase.
- `phase-0-export-boundary.md` depends on no earlier phase.
- Recommended execution order is `0 -> 1 -> 2 -> 3` for minimal blast radius.

## Global validation strategy
1. Baseline snapshot before the migration starts.
```bash
python - <<'PY'
import json
import continuous_refactoring

from pathlib import Path

out = Path("migrations/src-continuous-refactoring-agent-py-20260416T001254")
out.mkdir(parents=True, exist_ok=True)
baseline = {
    "exports": sorted(continuous_refactoring.__all__),
}
out.joinpath("phase-0-baseline.json").write_text(
    json.dumps(baseline, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print("wrote", out.joinpath("phase-0-baseline.json"))
PY
```
2. Per phase, run the phase ready check and then run the phase-specific validation block below.
3. Per phase scope check for touched source files:
```bash
python - <<'PY'
import subprocess
import sys

ALLOWED = {
    "src/continuous_refactoring/__init__.py",
    "src/continuous_refactoring/config.py",
    "src/continuous_refactoring/cli.py",
    "src/continuous_refactoring/prompts.py",
    "src/continuous_refactoring/phases.py",
}
changed = {
    path.strip()
    for path in subprocess.check_output(["git", "diff", "--name-only", "HEAD", "--", "src/continuous_refactoring"], text=True).splitlines()
}
bad = sorted(path for path in changed if path not in ALLOWED)
if bad:
    print("out-of-scope source edits:", ", ".join(bad))
    sys.exit(1)
print("scope ok")
PY
```
4. All phases keep package importability:
```bash
python - <<'PY'
import continuous_refactoring
assert hasattr(continuous_refactoring, "__all__")
assert isinstance(continuous_refactoring.__all__, tuple)
print("import ok")
PY
```
5. Run the phase-specific validation commands before marking `ready_when` complete.

## Phase-specific readiness and validation
Each phase file below contains:
- Ordered implementation steps
- Mechanical `ready_when` gates
- Validation commands and pass/fail conditions
- Why phase is independently shippable
