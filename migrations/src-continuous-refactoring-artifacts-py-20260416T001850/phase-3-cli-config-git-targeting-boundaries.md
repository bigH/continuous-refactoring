# Phase 3 — CLI/config/git/targeting boundary cleanup (`config.py`, `cli.py`, `git.py`, `targeting.py`)

## Scope
`src/continuous_refactoring/cli.py`, `src/continuous_refactoring/config.py`, `src/continuous_refactoring/git.py`, `src/continuous_refactoring/targeting.py`.

## Objective
Move taste/path helper ownership to `config.py` and keep CLI entry behavior unchanged.

## Instructions
1. In `config.py`, expose taste path helper(s) used by CLI flows.
2. Remove local CLI-only copies of those helpers from `cli.py`.
3. Replace CLI callsites to use `config` helpers.
4. Keep parser flags, return codes, and invocation flow unchanged.
5. Keep `git.py` and `targeting.py` APIs unchanged; apply naming/clarity cleanup only where artifact-related paths are touched.
6. Keep any temporary compatibility fallback names only when strictly tied to a narrow transition path.

## Ready when (machine-checkable)
1. Scope guard:
```bash
python - <<'PY'
import subprocess

allowed = {
    "src/continuous_refactoring/artifacts.py",
    "src/continuous_refactoring/loop.py",
    "src/continuous_refactoring/cli.py",
    "src/continuous_refactoring/config.py",
    "src/continuous_refactoring/git.py",
    "src/continuous_refactoring/targeting.py",
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
2. CLI contains no local taste-path helper implementations:
```bash
python - <<'PY'
import ast
from pathlib import Path

forbidden = {"_resolve_taste_path", "_taste_settle_path", "_resolve_taste_root"}
body = Path("src/continuous_refactoring/cli.py").read_text(encoding="utf-8")
tree = ast.parse(body)
funcs = {
    node.name
    for node in ast.walk(tree)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
found = sorted(forbidden.intersection(funcs))
if found:
    raise SystemExit(f"unexpected local helper definitions: {found}")
print("helper ownership check passed")
PY
```
3. CLI uses config-owned helper symbols:
```bash
python - <<'PY'
import ast
from pathlib import Path

tree = ast.parse(Path("src/continuous_refactoring/cli.py").read_text(encoding="utf-8"))
allowed_helper_names = {"resolve_taste_path", "resolve_taste_settle_path", "resolve_taste_root"}
used = {
    node.id
    for node in ast.walk(tree)
    if isinstance(node, ast.Name)
}
if not used.intersection(allowed_helper_names):
    raise SystemExit("no expected config helper names found in CLI usage")
print("config helper usage check passed")
PY
```
4. Parser contract stays intact:
```bash
python - <<'PY'
from continuous_refactoring.cli import build_parser

def parse(argv):
    parser = build_parser()
    parsed = parser.parse_args(argv)
    assert parsed.command is not None

parse(["run", "--with", "codex", "--model", "m", "--effort", "e", "--scope-instruction", "scope", "--max-refactors", "1"])
parse(["run-once", "--with", "codex", "--model", "m", "--effort", "e", "--scope-instruction", "scope"])
parse(["taste", "--global", "--with", "codex", "--model", "m", "--effort", "e", "--upgrade"])
parse(["upgrade"])
print("parser contract ok")
PY
```

## Validation
1. CLI tests:
```bash
pytest -q tests/test_cli_init_taste.py tests/test_cli_taste_warning.py tests/test_cli_review.py tests/test_cli_upgrade.py
pytest -q tests/test_taste_interview.py tests/test_taste_refine.py tests/test_taste_upgrade.py
```
2. Config tests:
```bash
pytest -q tests/test_config.py
```
3. Git and targeting tests:
```bash
pytest -q tests/test_git_branching.py tests/test_targeting.py
```
4. Compile gate:
```bash
python -m py_compile src/continuous_refactoring/cli.py src/continuous_refactoring/config.py src/continuous_refactoring/git.py src/continuous_refactoring/targeting.py
```

## Independent shippability
If this phase passes, CLI externally behaves the same while taste path logic is properly rooted at config boundaries.
