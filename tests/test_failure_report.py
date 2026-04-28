from __future__ import annotations

from pathlib import Path

import pytest

import continuous_refactoring.failure_report as failure_report
from continuous_refactoring.artifacts import RunArtifacts
from continuous_refactoring.config import register_project
from continuous_refactoring.decisions import DecisionRecord
from continuous_refactoring.failure_report import (
    _yaml_scalar,
    effective_record,
    persist_decision,
    write,
)


def _artifacts(root: Path) -> RunArtifacts:
    root.mkdir(parents=True, exist_ok=True)
    return RunArtifacts(
        root=root,
        run_id="20260421T120000-000000",
        repo_root=root.parent / "repo",
        agent="codex",
        model="gpt-test",
        effort="xhigh",
        test_command="uv run pytest",
        events_path=root / "events.jsonl",
        summary_path=root / "summary.json",
        log_path=root / "run.log",
        started_at="2026-04-21T12:00:00.000-07:00",
    )


def _record(**overrides: object) -> DecisionRecord:
    values = {
        "decision": "retry",
        "retry_recommendation": "same-target",
        "target": "src/example.py",
        "call_role": "validation",
        "phase_reached": "refactor",
        "failure_kind": "validation-failed",
        "summary": "Validation failed",
        "next_retry_focus": "Fix the failing assertion.",
    }
    values.update(overrides)
    return DecisionRecord(**values)


def test_effective_record_abandons_after_max_attempts() -> None:
    record = _record(
        summary="Still red",
        next_retry_focus="Preserve this focus",
        retry_used=7,
        agent_stdout_path=Path("/tmp/agent.stdout.log"),
    )

    updated = effective_record(record, retry=3, max_attempts=3)

    assert updated.decision == "abandon"
    assert updated.retry_recommendation == "new-target"
    assert updated.summary == "Exhausted 3 attempts. Last failure: Still red"
    assert updated.next_retry_focus == "Preserve this focus"
    assert updated.retry_used == 7
    assert updated.agent_stdout_path == Path("/tmp/agent.stdout.log")


def test_effective_record_keeps_retry_before_max_attempts() -> None:
    record = _record()

    assert effective_record(record, retry=2, max_attempts=3) is record
    assert effective_record(record, retry=3, max_attempts=None) is record


def test_yaml_scalar_formats_representative_values() -> None:
    assert _yaml_scalar(None) == '""'
    assert _yaml_scalar(True) == "true"
    assert _yaml_scalar(False) == "false"
    assert _yaml_scalar(17) == "17"
    assert _yaml_scalar("plain") == '"plain"'
    assert _yaml_scalar("two\nlines") == '"two\\nlines"'
    assert _yaml_scalar('quote " and slash \\') == '"quote \\" and slash \\\\"'


def test_write_emits_snapshot_header_and_body(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    project = register_project(repo_root)
    artifacts = _artifacts(tmp_path / "artifacts")
    record = _record(
        agent_last_message_path=artifacts.root / "attempt-001" / "agent.md",
        agent_stdout_path=artifacts.root / "attempt-001" / "agent.stdout.log",
        agent_stderr_path=Path("/outside/agent.stderr.log"),
        tests_stdout_path=artifacts.root / "attempt-001" / "tests.stdout.log",
        tests_stderr_path=None,
    )

    snapshot_path = write(
        repo_root,
        artifacts,
        target=record.target,
        attempt=2,
        retry=4,
        validation_command="uv run pytest",
        record=record,
    )

    assert snapshot_path.name == (
        "20260421T120000-000000-attempt-002-retry-04-validation.md"
    )
    assert snapshot_path.parent == project.project_dir / "failures"
    content = snapshot_path.read_text(encoding="utf-8")
    assert f"project_uuid: \"{project.entry.uuid}\"" in content
    assert f"repo_root: \"{repo_root}\"" in content
    assert "target: \"src/example.py\"" in content
    assert "attempt: 2" in content
    assert "retry: 4" in content
    assert "call_role: \"validation\"" in content
    assert "validation_command: \"uv run pytest\"" in content
    assert "agent_last_message: \"attempt-001/agent.md\"" in content
    assert "agent_stderr: \"/outside/agent.stderr.log\"" in content
    assert "tests_stderr: \"\"" in content
    assert "# Reason for Failure" in content
    assert "## What failed\nValidation failed" in content
    assert "Retry the same target on the next attempt. Focus: Fix the failing assertion." in content


def test_write_replaces_dots_in_call_role_snapshot_name(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifacts = _artifacts(tmp_path / "artifacts")
    record = _record(call_role="planner.review")

    snapshot_path = write(
        repo_root,
        artifacts,
        target=record.target,
        attempt=1,
        retry=1,
        validation_command="uv run pytest",
        record=record,
    )

    assert snapshot_path.name == (
        "20260421T120000-000000-attempt-001-retry-01-planner-review.md"
    )


def test_write_preserves_existing_snapshot_on_replace_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifacts = _artifacts(tmp_path / "artifacts")
    record = _record()

    snapshot_path = write(
        repo_root,
        artifacts,
        target=record.target,
        attempt=1,
        retry=1,
        validation_command="uv run pytest",
        record=record,
    )
    snapshot_path.write_text("previous snapshot\n", encoding="utf-8")

    def fail_replace(_src: object, _dst: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(failure_report.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        write(
            repo_root,
            artifacts,
            target=record.target,
            attempt=1,
            retry=1,
            validation_command="uv run pytest",
            record=record,
        )

    assert snapshot_path.read_text(encoding="utf-8") == "previous snapshot\n"
    assert list(snapshot_path.parent.glob("*.tmp")) == []


def test_persist_decision_records_commit_without_failure_snapshot(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifacts = _artifacts(tmp_path / "artifacts")
    record = _record(
        decision="commit",
        retry_recommendation="none",
        failure_kind="none",
        summary="Ready to commit.",
    )
    failure_snapshot_calls = 0

    def fail_if_snapshot_dir_requested(_repo_root: Path) -> Path:
        nonlocal failure_snapshot_calls
        failure_snapshot_calls += 1
        raise AssertionError("commit path should not request failure snapshot storage")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        failure_report,
        "failure_snapshots_dir",
        fail_if_snapshot_dir_requested,
    )

    try:
        result = persist_decision(
            repo_root,
            artifacts,
            attempt=1,
            retry=2,
            validation_command="uv run pytest",
            record=record,
        )
    finally:
        monkeypatch.undo()

    assert result is None
    assert failure_snapshot_calls == 0
    stats = artifacts.attempts[1]
    assert stats.decision == "commit"
    assert stats.retry == 2
    assert stats.reason_doc_path is None
    assert not artifacts.events_path.exists()


def test_persist_decision_records_non_commit_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifacts = _artifacts(tmp_path / "artifacts")
    record = _record()

    result = persist_decision(
        repo_root,
        artifacts,
        attempt=1,
        retry=1,
        validation_command="uv run pytest",
        record=record,
    )

    assert result is not None
    assert result.exists()
    stats = artifacts.attempts[1]
    assert stats.decision == "retry"
    assert stats.reason_doc_path == str(result)
    events = artifacts.events_path.read_text(encoding="utf-8")
    assert '"event": "failure_doc_written"' in events
    assert '"event": "target_transition"' in events
