# Migration plan: artifacts-boundary-minimal

## Migration target
- ID: `src-continuous-refactoring-artifacts-py-20260416T001850`
- Chosen approach: `approaches/artifacts-boundary-minimal.md`
- Scope label: `local-cluster`
- Primary target module: `src/continuous_refactoring/artifacts.py`

## Scope
Editable files for this migration:
- `src/continuous_refactoring/artifacts.py`
- `src/continuous_refactoring/loop.py`
- `src/continuous_refactoring/cli.py`
- `src/continuous_refactoring/config.py`
- `src/continuous_refactoring/git.py`
- `src/continuous_refactoring/targeting.py`

`agent.py` is intentionally out of scope in this pass so behavior risk stays bounded.

Explicitly out of scope:
- `src/continuous_refactoring/__init__.py`
- `src/continuous_refactoring/planning.py`
- `src/continuous_refactoring/phases.py`
- `src/continuous_refactoring/routing.py`
- `src/continuous_refactoring/scope_expansion.py`

## Why this order is low-risk
- Phase 1 contains the persistence contract and keeps changes inside one module.
- Phase 2 only consumes those contracts from `loop.py` and removes duplicated status vocabulary.
- Phase 3 moves taste/path helpers toward config ownership and keeps CLI, git, and targeting behavior stable.
- Each phase is behavior-preserving and independently shippable.
- No rollout gating is introduced; shipped systems receive direct compatibility-preserving changes.

## Phase order and dependency chain
1. `phase-1-artifacts-contract-boundary.md`
2. `phase-2-loop-status-alignment.md` depends on phase 1 outputs
3. `phase-3-cli-config-git-targeting-boundaries.md` depends on phase 1 and phase 2 outputs

## Global validation strategy
1. Per-phase readiness gates from each phase file must pass before execution.
2. After each phase: run phase-specific `py_compile` and test slice.
3. After each phase: confirm package import path remains valid.
4. No phase may merge unless previous phase is green and scope is clean by `git diff --name-only` checks.

Suggested cross-phase smoke commands:
```bash
python -m py_compile src/continuous_refactoring/artifacts.py src/continuous_refactoring/loop.py src/continuous_refactoring/cli.py src/continuous_refactoring/config.py src/continuous_refactoring/git.py src/continuous_refactoring/targeting.py
python - <<'PY'
import continuous_refactoring
print(continuous_refactoring.__name__)
PY
```

## Execution policy
- Stop on first failed ready_when or validation step and fix in the same phase.
- Keep the repository buildable at each phase boundary.
- No schema-breaking changes; maintain compatibility for shipped systems.
