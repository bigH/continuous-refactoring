# Phase 2 — Core boundary hardening

## Scope (hard allowed set)

1. `src/continuous_refactoring/artifacts.py`
2. `src/continuous_refactoring/agent.py`
3. `src/continuous_refactoring/config.py`
4. `src/continuous_refactoring/git.py`
5. `src/continuous_refactoring/targeting.py`

No edits in `loop.py`, `cli.py`, or `__init__.py` in this phase.

## Goal

Add causal chains (`raise ... from error`) at core module boundaries only, without changing success-path behavior or user-facing status contracts.

## Detailed instructions

1. In `artifacts.py`, add chaining to all low-level persistence and path failures that map into `ContinuousRefactorError`.
2. In `agent.py`, wrap failures in command spawn, stream wiring, and process IO setup with causal chains.
3. In `config.py`, wrap parse/load/save and command execution failures with causal chains at config/module boundaries.
4. In `git.py`, wrap subprocess launch/status failures into `ContinuousRefactorError` with preserved causes.
5. In `targeting.py`, preserve parse and subprocess causes in failure paths as root-cause chained errors.
6. Keep message payload text unchanged unless it blocks causal wrap clarity.
7. Keep artifact payloads and event summary order unchanged.

## Ready when (machine-checkable)

1. `uv run pytest tests/test_continuous_refactoring.py::test_run_observed_command_writes_timestamped_logs`
2. `uv run pytest tests/test_git_branching.py::test_run_observed_command_timeout tests/test_git_branching.py::test_agent_killed_when_stdout_stalled`
3. `uv run pytest tests/test_continuous_refactoring.py::test_run_agent_interactive_until_settled_requests_graceful_exit_after_settle`
4. `uv run pytest tests/test_continuous_refactoring.py::test_run_agent_interactive_until_settled_ignores_stale_settle_file`
5. `uv run pytest tests/test_config.py::test_load_manifest_empty tests/test_config.py::test_load_manifest_rejects_non_object_payload`
6. `uv run pytest tests/test_targeting.py::test_load_targets_jsonl_skips_invalid`
7. `uv run pytest tests/test_run.py::test_run_pushes_after_commit`
8. `uv run pytest tests/test_run_once.py::test_run_once_validation_gate`
9. `uv run python - <<'PY'
from datetime import datetime
from pathlib import Path
import json
import os
import tempfile
from continuous_refactoring.artifacts import create_run_artifacts

root = Path(tempfile.mkdtemp(prefix="cr-phase2-"))
os.environ["TMPDIR"] = str(root)
artifacts = create_run_artifacts(
    root,
    agent="codex",
    model="fake-model",
    effort="medium",
    test_command="pytest -q",
)
artifacts.log("info", "phase-2 smoke")
artifacts.finish("completed")
assert artifacts.summary_path.exists(), artifacts.summary_path
assert artifacts.events_path.exists(), artifacts.events_path
assert artifacts.log_path.exists(), artifacts.log_path
summary = json.loads(artifacts.summary_path.read_text(encoding="utf-8"))
assert summary["final_status"] == "completed"
assert summary["artifact_root"].endswith(artifacts.run_id)
start_dt = datetime.fromisoformat(summary["started_at"])
finish_dt = datetime.fromisoformat(summary["finished_at"])
assert finish_dt >= start_dt
log_text = artifacts.log_path.read_text(encoding="utf-8")
assert "phase-2 smoke" in log_text
PY`
10. `git diff --name-only -- src/continuous_refactoring/artifacts.py src/continuous_refactoring/agent.py src/continuous_refactoring/config.py src/continuous_refactoring/git.py src/continuous_refactoring/targeting.py` includes only those files.

## Validation

1. Core module edits are limited to the listed files.
2. `events.jsonl`, `run.log`, and `summary.json` behavior remains present and writable.
3. No behavioral assertions rely on changed success return values or order.
