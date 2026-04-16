# Phase 3: orchestration-boundaries-loop-phases-targeting

## Objective

Normalize orchestration and targeting boundary behavior so lower-layer causes are preserved when translated, without changing existing status semantics.

## Scope

- `src/continuous_refactoring/loop.py`
- `src/continuous_refactoring/phases.py`
- `src/continuous_refactoring/targeting.py`

Out of scope:
- `git.py`, `config.py`

## Instructions

1. In `loop.py`:
   1. Preserve status constants and transitions exactly.
   2. If and only if a lower-layer exception is rewrapped at loop boundary, use `from error`.
   3. Ensure `_route_and_run`, `run_once`, and `run_loop` do not introduce duplicate wraps where `git.py` already translated cause.
2. In `phases.py`:
   1. Preserve `check_phase_ready` and `execute_phase` behavior.
   2. Keep any ownership errors explicit and ensure no duplicate re-wraps with lost signal.
3. In `targeting.py`:
   1. Wrap `subprocess.run([...])` failures (`OSError`, `subprocess.SubprocessError`) in `list_tracked_files` as `ContinuousRefactorError(... ) from error`.
   2. Keep non-zero returncode translation intentionally message-based (no underlying exception exists there, so no `__cause`).
4. No changes outside migration scope.

## Ready_when (machine-checkable)

1. In targeted modules, every `raise ContinuousRefactorError(...)` inside an except-handler with a bound exception variable has an explicit `from <var>` cause.

```bash
python - <<'PY'
import ast
from pathlib import Path

modules = (
    Path('src/continuous_refactoring/loop.py'),
    Path('src/continuous_refactoring/phases.py'),
    Path('src/continuous_refactoring/targeting.py'),
)

for path in modules:
    text = path.read_text(encoding='utf-8')
    tree = ast.parse(text)
    parent = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node

    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise):
            continue
        if not isinstance(node.exc, ast.Call):
            continue
        func = node.exc.func
        if not (isinstance(func, ast.Name) and func.id == 'ContinuousRefactorError'):
            continue

        p = parent.get(node)
        while p is not None and not isinstance(p, ast.ExceptHandler):
            p = parent.get(p)
        if p is None:
            continue
        if p.name is None:
            # no bound variable => cannot preserve explicit cause by construction
            continue
        assert node.cause is not None, f'{path}:{node.lineno} missing `from` under except {p.name}'

print('ok')
PY
```

2. `git diff --name-only -- src/continuous_refactoring/loop.py src/continuous_refactoring/phases.py src/continuous_refactoring/targeting.py` includes only these files plus migration docs.

## Validation

1. `uv run pytest tests/test_loop_migration_tick.py::test_eligible_ready_migration_advances_phase`
2. `uv run pytest tests/test_phases.py::test_execute_phase_test_failure_reverts_workspace`
3. `uv run pytest tests/test_run.py::test_run_stops_after_max_consecutive_failures`
4. `uv run pytest tests/test_targeting.py::test_load_targets_jsonl_skips_invalid`
5. `uv run pytest tests/test_run_once.py::test_run_once_validation_gate`

## Exit criteria

- No duplicate wraps introduced where signal was already translated in lower modules.
- Status names and outcomes unchanged.
- Targeting subprocess invocation failures are cause-preserving and non-zero exit-code errors retain existing user-facing behavior.
