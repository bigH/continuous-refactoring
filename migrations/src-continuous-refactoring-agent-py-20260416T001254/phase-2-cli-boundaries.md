# Phase 2 — Move CLI policy into config and keep CLI orchestration pure

## Scope
`src/continuous_refactoring/cli.py` only.

## Objective
Keep CLI handlers responsible only for orchestration and user-facing text; move reusable resolution/normalization logic to config helpers added in phase 1.

## Instructions
1. Replace uses of local helper logic for taste path, settle path, and live migration path checks with calls into phase 1 helpers.
2. Keep `SystemExit` conversions in CLI handlers and preserve their existing intent: same exit code and same user-visible error strings for known user errors.
3. Keep parser surface unchanged (argument names, subcommands, required flags).
4. Keep `parse_max_attempts` unchanged and unit-tested.
5. Keep module-level exports stable unless explicitly documented and reviewed.

## Readiness gates (machine-checkable)
1. Scope guard:
```bash
python - <<'PY'
import subprocess
import sys

changed = {line.strip() for line in subprocess.check_output(["git", "diff", "HEAD", "--", "src/continuous_refactoring"], text=True).splitlines()}
bad = [p for p in changed if p not in {"src/continuous_refactoring/cli.py"} and p.endswith(".py")]
if bad:
    print("out-of-scope for phase 2:", ", ".join(sorted(bad)))
    sys.exit(1)
print("scope ok")
PY
```
2. Parser and help contract is stable (exact parse objects):
```bash
python - <<'PY'
from continuous_refactoring.cli import build_parser

parser = build_parser()
for argv in (
    ["init"],
    ["taste", "--global"],
    ["run-once", "--with", "codex", "--model", "m", "--effort", "e", "--scope-instruction", "scope"],
    ["run", "--with", "codex", "--model", "m", "--effort", "e", "--scope-instruction", "scope", "--max-refactors", "1"],
    ["upgrade"],
    ["review", "list"],
    ["review", "perform", "example", "--with", "codex", "--model", "m", "--effort", "e"],
):
    parsed = parser.parse_args(argv)
    assert parsed.command is not None
print("parser smoke ok")
PY
```
3. Error output/exit code parity matrix is machine-checked against baseline capture:
```bash
python - <<'PY'
import io
import contextlib
import json
from pathlib import Path

from continuous_refactoring.cli import build_parser

parser = build_parser()
baseline = Path(
    "migrations/src-continuous-refactoring-agent-py-20260416T001254/phase-2-parser-baseline.json"
)
cases = [
    ["run"],
    ["run-once", "--with", "codex"],
    ["taste", "--upgrade"],
]

def capture(argv):
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        try:
            parser.parse_args(argv)
            return 0, ""
        except SystemExit as err:
            return err.code, stderr.getvalue()

captured = {}
for argv in cases:
    code, text = capture(argv)
    captured[" ".join(argv)] = {"code": code, "stderr_prefix": text.splitlines()[-1] if text else ""}

if not baseline.exists():
    baseline.write_text(json.dumps(captured, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    raise SystemExit(f"baseline created at {baseline} (rerun to validate)")

expected = json.loads(baseline.read_text(encoding="utf-8"))
if captured != expected:
    raise SystemExit(f"parser parity mismatch\ncaptured={captured}\nexpected={expected}")
print("parser error capture run")
PY
```
4. CLI behavior smoke: `_resolve_taste_path`, `_taste_settle_path`, and inline live-dir path checks are removed from `cli.py`.
Use:
`rg "_resolve_taste_path|_taste_settle_path|inside the repo|escape" src/continuous_refactoring/cli.py` should return only non-behavioral references.

## Validation
1. CLI stability and warning behavior:
```bash
pytest -q tests/test_cli_taste_warning.py tests/test_main_entrypoint.py tests/test_taste_refine.py tests/test_taste_interview.py tests/test_taste_upgrade.py
```
2. Parser contract checks:
```bash
pytest -q tests/test_taste_refine.py::test_taste_subparser_accepts_refine_flags
```
3. Boundaries:
`python - <<'PY'
from continuous_refactoring import cli
assert hasattr(cli, "build_parser")
assert hasattr(cli, "cli_main")
assert hasattr(cli, "parse_max_attempts")
print("cli exports ok")
PY`

## Independent shippability
If any CLI semantics diverge unexpectedly, revert only this file to restore parser/runtime behavior while keeping completed boundary work in `config.py`.
