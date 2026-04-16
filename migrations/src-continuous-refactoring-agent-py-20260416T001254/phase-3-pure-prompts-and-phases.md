# Phase 3 — Pure prompt/phase boundary hardening (`prompts.py`, `phases.py`)

## Scope
`src/continuous_refactoring/prompts.py` and `src/continuous_refactoring/phases.py` only.

## Objective
Keep these modules as deterministic boundary helpers: pure composition and parsing only.

## Instructions
1. Ensure `compose_*` functions remain deterministic for the same inputs.
2. Keep `check_phase_ready` and `execute_phase` behavior signatures unchanged.
3. Keep imports in `phases.py` limited to required collaborators and avoid introducing orchestration policy.
4. Do not modify `agent.py` or `loop.py` in this phase.

## Readiness gates (machine-checkable)
1. Scope guard:
```bash
python - <<'PY'
import subprocess
import sys

allowed = {
    "src/continuous_refactoring/prompts.py",
    "src/continuous_refactoring/phases.py",
}
changed = {line.strip() for line in subprocess.check_output(["git", "diff", "HEAD", "--", "src/continuous_refactoring"], text=True).splitlines()}
bad = [p for p in changed if p not in allowed and p.endswith(".py")]
if bad:
    print("out-of-scope edits:", ", ".join(sorted(bad)))
    sys.exit(1)
print("scope ok")
PY
```
2. Determinism property checks:
```bash
python - <<'PY'
import random
from continuous_refactoring.config import TASTE_CURRENT_VERSION
from continuous_refactoring.migrations import MigrationManifest, PhaseSpec
from continuous_refactoring.prompts import compose_phase_execution_prompt, compose_phase_ready_prompt
from continuous_refactoring.phases import generate_phase_branch_name

random.seed(20260416)

manifest = MigrationManifest(
    name="mig",
    created_at="2026-01-01T00:00:00.000Z",
    last_touch="2026-01-02T00:00:00.000Z",
    wake_up_on=None,
    awaiting_human_review=False,
    status="in-progress",
    current_phase=1,
    phases=(PhaseSpec(name="migrate", file="phase-1.md", done=False, ready_when="ready"),),
)
phase = manifest.phases[0]
taste = "- taste-scoping-version: " + str(TASTE_CURRENT_VERSION)

for _ in range(100):
    m = f"mig-{random.randint(0, 1_000_000)}"
    n = f"phase-{random.randint(0, 1_000)}"
    branch = generate_phase_branch_name(m, 3, n)
    assert branch.startswith("migration/"), branch
    assert branch.count("/") == 2
    assert branch == generate_phase_branch_name(m, 3, n)

rp1 = compose_phase_ready_prompt(phase, manifest)
rp2 = compose_phase_ready_prompt(phase, manifest)
ep1 = compose_phase_execution_prompt(phase, manifest, taste)
ep2 = compose_phase_execution_prompt(phase, manifest, taste)

assert rp1 == rp2
assert ep1 == ep2
assert phase.name in rp1 and manifest.name in rp1 and phase.file in rp1
assert "ready: yes" in rp1 and "ready: no" in rp1 and "ready: unverifiable" in rp1
print("determinism checks ok")
PY
```
3. CLI-facing semantics preserved by return contracts:
- `check_phase_ready` still raises `ContinuousRefactorError` when no parseable verdict exists.
- `execute_phase` still returns status in `{"done","awaiting_human_review","failed"}` and updates manifest on success.
4. Import surface check:
`rg "import continuous_refactoring.agent|from continuous_refactoring.agent import" src/continuous_refactoring/phases.py` should return only existing required imports.

## Validation
1. Keep output contracts by running property + existing tests:
```bash
pytest -q tests/test_prompts.py tests/test_phases.py
```
2. Extended property checks (recommended for taste preference):
```bash
python - <<'PY'
from continuous_refactoring.phases import generate_phase_branch_name

cases = [
    ("Rework Auth Module!", 1, "Core Migration", "migration/rework-auth-module/phase-1-core-migration"),
    ("A B  -- C", 2, "Refactor/Docs", "migration/a-b-c/phase-2-refactor-docs"),
]
for name, idx, phase, expect in cases:
    assert generate_phase_branch_name(name, idx, phase) == expect
PY
```

## Independent shippability
This phase does not depend on phase 2 and does not affect CLI/parser behavior in `cli.py`.
