"""Failure snapshot persistence."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from continuous_refactoring.config import failure_snapshots_dir, register_project
from continuous_refactoring.decisions import DecisionRecord

if TYPE_CHECKING:
    from continuous_refactoring.artifacts import RunArtifacts

__all__ = [
    "effective_record",
    "persist_decision",
    "write",
]


def _relative_path(path: Path | None, root: Path) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _yaml_scalar(value: object) -> str:
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value))


def write(
    repo_root: Path,
    artifacts: RunArtifacts,
    *,
    target: str,
    attempt: int,
    retry: int,
    validation_command: str,
    record: DecisionRecord,
) -> Path:
    project = register_project(repo_root)
    snapshot_dir = failure_snapshots_dir(repo_root)
    snapshot_name = (
        f"{artifacts.run_id}-attempt-{attempt:03d}-retry-{retry:02d}-"
        f"{record.call_role.replace('.', '-')}.md"
    )
    snapshot_path = snapshot_dir / snapshot_name
    agent_last_message = _relative_path(record.agent_last_message_path, artifacts.root)
    agent_stdout = _relative_path(record.agent_stdout_path, artifacts.root)
    agent_stderr = _relative_path(record.agent_stderr_path, artifacts.root)
    tests_stdout = _relative_path(record.tests_stdout_path, artifacts.root)
    tests_stderr = _relative_path(record.tests_stderr_path, artifacts.root)
    content = "\n".join([
        "---",
        f"schema_version: {_yaml_scalar(1)}",
        f"project_uuid: {_yaml_scalar(project.entry.uuid)}",
        f"repo_root: {_yaml_scalar(str(repo_root))}",
        f"run_id: {_yaml_scalar(artifacts.run_id)}",
        f"target: {_yaml_scalar(target)}",
        f"attempt: {_yaml_scalar(attempt)}",
        f"retry: {_yaml_scalar(retry)}",
        f"call_role: {_yaml_scalar(record.call_role)}",
        f"phase_reached: {_yaml_scalar(record.phase_reached)}",
        f"decision: {_yaml_scalar(record.decision)}",
        f"retry_recommendation: {_yaml_scalar(record.retry_recommendation)}",
        f"failure_kind: {_yaml_scalar(record.failure_kind)}",
        f"summary: {_yaml_scalar(record.summary)}",
        f"validation_command: {_yaml_scalar(validation_command)}",
        f"artifact_root: {_yaml_scalar(str(artifacts.root))}",
        f"agent_last_message: {_yaml_scalar(agent_last_message)}",
        f"agent_stdout: {_yaml_scalar(agent_stdout)}",
        f"agent_stderr: {_yaml_scalar(agent_stderr)}",
        f"tests_stdout: {_yaml_scalar(tests_stdout)}",
        f"tests_stderr: {_yaml_scalar(tests_stderr)}",
        "---",
        "",
        "# Reason for Failure",
        "",
        "## What failed",
        record.summary,
        "",
        "## Why it failed",
        (
            f"The runner stopped at `{record.call_role}` "
            f"and decided `{record.decision}` / `{record.retry_recommendation}` "
            f"because `{record.failure_kind}` was the safest next move."
        ),
        "",
        "## Next step",
        _next_step_text(record),
        "",
        "## Evidence",
        f"- Run artifacts: {artifacts.root}",
        f"- Latest agent message: {agent_last_message or '(not available)'}",
        f"- Agent stdout: {agent_stdout or '(not available)'}",
        f"- Agent stderr: {agent_stderr or '(not available)'}",
        f"- Tests stdout: {tests_stdout or '(not available)'}",
        f"- Tests stderr: {tests_stderr or '(not available)'}",
        "",
    ])
    snapshot_path.write_text(content, encoding="utf-8")
    return snapshot_path


def _next_step_text(record: DecisionRecord) -> str:
    if record.decision == "retry":
        focus = f" Focus: {record.next_retry_focus}" if record.next_retry_focus else ""
        return f"Retry the same target on the next attempt.{focus}"
    if record.decision == "abandon":
        return "Abandon this target and move on to a different target."
    if record.decision == "blocked":
        return "Pause for human review before attempting more automated work."
    return "Commit the validated result and continue normally."


def effective_record(
    record: DecisionRecord,
    *,
    retry: int,
    max_attempts: int | None,
) -> DecisionRecord:
    if record.decision != "retry" or record.retry_recommendation != "same-target":
        return record
    if max_attempts is None or retry < max_attempts:
        return record
    return replace(
        record,
        decision="abandon",
        retry_recommendation="new-target",
        summary=f"Exhausted {max_attempts} attempts. Last failure: {record.summary}",
    )


def persist_decision(
    repo_root: Path,
    artifacts: RunArtifacts,
    *,
    attempt: int,
    retry: int,
    validation_command: str,
    record: DecisionRecord,
) -> Path | None:
    if record.decision == "commit":
        artifacts.update_attempt(
            attempt,
            target=record.target,
            retry=retry,
            call_role=record.call_role,
            phase_reached=record.phase_reached,
            decision=record.decision,
            retry_recommendation=record.retry_recommendation,
            failure_kind=record.failure_kind,
            failure_summary=record.summary,
            reason_doc_path=None,
        )
        return None

    reason_doc = write(
        repo_root,
        artifacts,
        target=record.target,
        attempt=attempt,
        retry=retry,
        validation_command=validation_command,
        record=record,
    )
    artifacts.log(
        "WARN",
        f"failure snapshot written: {reason_doc}",
        event="failure_doc_written",
        attempt=attempt,
        retry=retry,
        target=record.target,
        call_role=record.call_role,
        phase_reached=record.phase_reached,
        reason_doc_path=str(reason_doc),
    )
    artifacts.log_transition(
        attempt=attempt,
        retry=retry,
        target=record.target,
        call_role=record.call_role,
        phase_reached=record.phase_reached,
        decision=record.decision,
        retry_recommendation=record.retry_recommendation,
        failure_kind=record.failure_kind,
        summary=record.summary,
        reason_doc_path=reason_doc,
    )
    return reason_doc
