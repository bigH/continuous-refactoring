# Phase 4: prompt-surface-guardrails

## Objective

Keep prompt text in sync with boundary contract changes while preventing behavior changes to prompt composition code.

## Scope

- `src/continuous_refactoring/prompts.py`

## Instructions

1. Compare prompt copy against current status transition wording and taste directives.
2. Apply edits only when they are boundary-text corrections.
3. If no correction is needed, leave file unchanged.
4. Any edits must stay inside top-level constant assignments (e.g., `DEFAULT_*`, `PLANNING_*`, `PHASE_*`) and must not alter function bodies.
5. Keep message changes minimal and deterministic.

## Ready_when (machine-checkable)

1. If `git diff --name-only src/continuous_refactoring/prompts.py` is empty, ready_when passes immediately.
2. Otherwise, run structural AST gate below:

```bash
python - <<'PY'
import ast
from pathlib import Path
import subprocess

old = subprocess.check_output(['git', 'show', 'HEAD:src/continuous_refactoring/prompts.py'], text=True)
new = Path('src/continuous_refactoring/prompts.py').read_text(encoding='utf-8')

t_old = ast.parse(old)
t_new = ast.parse(new)

# function/class definitions must be identical
for name, tb, tn in [
    (n.name, n, dict((x.name, x) for x in t_new.body if isinstance(x, ast.FunctionDef)).get(n.name))
    for n in [n for n in t_old.body if isinstance(n, ast.FunctionDef)]
]:
    if tn is None:
        raise SystemExit(f'function {name} added/removed')
    if ast.dump(n) != ast.dump(tn):
        raise SystemExit(f'function changed: {name}')

# imports and __all__ should be stable
for kind in ('Import', 'ImportFrom'):
    old_nodes = [n for n in t_old.body if isinstance(n, getattr(ast, kind))]
    new_nodes = [n for n in t_new.body if isinstance(n, getattr(ast, kind))]
    if len(old_nodes) != len(new_nodes):
        raise SystemExit('import topology changed')

# allow changed assignments only for non-call top-level UPPERCASE constants
old_assign = {tuple(getattr(t, 'id') for t in n.targets if isinstance(t, ast.Name)): n
              for n in t_old.body if isinstance(n, ast.Assign)}
new_assign = {tuple(getattr(t, 'id') for t in n.targets if isinstance(t, ast.Name)): n
              for n in t_new.body if isinstance(n, ast.Assign)}
if old_assign.keys() != new_assign.keys():
    raise SystemExit('assignment names changed')

for name, old_node in old_assign.items():
    new_node = new_assign[name]
    old_target = name[0]
    if ast.unparse(old_node.value) == ast.unparse(new_node.value):
        continue
    if old_target != old_target.upper():
        raise SystemExit(f'non-constant assignment changed: {old_target}')
    for v in (old_node.value, new_node.value):
        if not isinstance(v, (ast.Constant, ast.JoinedStr, ast.BinOp)):
            raise SystemExit(f'constant assignment is not string-like for {old_target}')

print('ok')
PY
```

3. `git diff --name-only` includes only `src/continuous_refactoring/prompts.py` plus migration docs.

## Validation

1. `uv run pytest tests/test_prompts.py::test_planning_prompts_reference_plan_artifacts`
2. `uv run pytest tests/test_prompts.py::test_full_prompt_prefers_target_scope_over_scope_instruction`
3. `uv run pytest tests/test_prompts.py::test_full_prompt_omits_blank_target_files`

## Exit criteria

- Either no change, or text-only top-level constant edits.
- No behavioral function changes in prompt composition.
