# Phase 4 — Validation lock

## Scope (hard allowed set)

1. `tests/test_continuous_refactoring.py`
2. `tests/test_git_branching.py`
3. `tests/test_targeting.py`
4. `tests/test_config.py`
5. `tests/test_run.py`
6. `tests/test_run_once.py`
7. `tests/test_loop_migration_tick.py`

No source module edits in this phase.

## Goal

Convert the migration into enforced tests with explicit assertions for causal chains and artifact persistence invariants.

## Detailed instructions

1. Add/adjust tests that assert `__cause__` is populated for boundary failures in
   `artifacts.py`, `agent.py`, `config.py`, `git.py`, and `targeting.py` paths.
2. Add/adjust tests that assert CLI/loop wrapping preserves causal context through `SystemExit` pathways.
3. Add a persisted ordering test that asserts `started_at <= finished_at` when summary is written after `finish(...)`.
4. Keep existing successful outcome assertions for interactive settlement, stalls, and branch/commit lifecycle.

## Ready when (machine-checkable)

1. `uv run pytest tests/test_continuous_refactoring.py::test_create_run_artifacts_uses_single_timestamp`
2. `uv run pytest tests/test_continuous_refactoring.py::test_run_observed_command_writes_timestamped_logs`
3. `uv run pytest tests/test_git_branching.py::test_run_observed_command_timeout`
4. `uv run pytest tests/test_git_branching.py::test_agent_killed_when_stdout_stalled`
5. `uv run pytest tests/test_config.py::test_load_manifest_rejects_non_object_payload`
6. `uv run pytest tests/test_targeting.py::test_load_targets_jsonl_skips_invalid`
7. `uv run pytest tests/test_run.py::test_run_exhausts_max_attempts_on_persistent_agent_failure`
8. `uv run pytest tests/test_run_once.py::test_run_once_timeout`
9. `uv run pytest tests/test_loop_migration_tick.py::test_6h_invariant_blocks_execution`
10. `uv run pytest tests/test_run.py::test_run_reports_and_records_driver_owned_commit_for_agent_commit tests/test_run_once.py::test_run_once_prints_and_records_commit`
11. `python - <<'PY'
from datetime import datetime
from pathlib import Path
import json
import os
import tempfile
from continuous_refactoring.artifacts import create_run_artifacts

root = Path(tempfile.mkdtemp(prefix='cr-phase4-'))
os.environ['TMPDIR'] = str(root)
artifacts = create_run_artifacts(
    root,
    agent='codex',
    model='fake-model',
    effort='medium',
    test_command='pytest -q',
)
artifacts.log('debug', 'phase-4 lock')
artifacts.finish('completed')
summary = json.loads(artifacts.summary_path.read_text(encoding='utf-8'))
assert summary['final_status'] == 'completed'
assert datetime.fromisoformat(summary['finished_at']) >= datetime.fromisoformat(summary['started_at'])
assert artifacts.events_path.exists()
assert artifacts.log_path.exists()
assert artifacts.summary_path.exists()
PY`
12. `python - <<'PY'
from pathlib import Path
paths = [
    Path('tests/test_continuous_refactoring.py'),
    Path('tests/test_git_branching.py'),
    Path('tests/test_targeting.py'),
    Path('tests/test_config.py'),
    Path('tests/test_run.py'),
    Path('tests/test_run_once.py'),
    Path('tests/test_loop_migration_tick.py'),
]
pattern_present = False
for path in paths:
    text = path.read_text(encoding='utf-8')
    if '__cause__ is not None' in text or '.__cause__' in text:
        pattern_present = True
        break
if not pattern_present:
    raise SystemExit('no __cause__ assertions found in phase-4 scope files')
PY`

## Validation

1. Causal-chain assertions are present in targeted tests.
2. Artifact persistence (`events.jsonl`, `run.log`, `summary.json`) is asserted in the updated test set.
3. Full phase-4 targeted suite and all earlier phase checks remain executable.
