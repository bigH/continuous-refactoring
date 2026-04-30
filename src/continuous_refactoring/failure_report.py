"""Failure snapshot persistence."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from continuous_refactoring.config import failure_snapshots_dir
from continuous_refactoring.decisions import DecisionRecord

if TYPE_CHECKING:
    from continuous_refactoring.artifacts import RunArtifacts

__all__ = [
    "effective_record",
    "persist_decision",
    "write",
]


@dataclass(frozen=True)
class SnapshotArtifactPaths:
    agent_last_message: str
    agent_stdout: str
    agent_stderr: str
    tests_stdout: str
    tests_stderr: str

    @classmethod
    def from_record(
        cls,
        record: DecisionRecord,
        artifact_root: Path,
    ) -> SnapshotArtifactPaths:
        return cls(
            agent_last_message=_relative_path(
                record.agent_last_message_path,
                artifact_root,
            ),
            agent_stdout=_relative_path(record.agent_stdout_path, artifact_root),
            agent_stderr=_relative_path(record.agent_stderr_path, artifact_root),
            tests_stdout=_relative_path(record.tests_stdout_path, artifact_root),
            tests_stderr=_relative_path(record.tests_stderr_path, artifact_root),
        )

    def front_matter_fields(self) -> dict[str, str]:
        return {
            "agent_last_message": self.agent_last_message,
            "agent_stdout": self.agent_stdout,
            "agent_stderr": self.agent_stderr,
            "tests_stdout": self.tests_stdout,
            "tests_stderr": self.tests_stderr,
        }

    def evidence_lines(self) -> list[str]:
        return [
            "- Latest agent message: "
            f"{self.agent_last_message or '(not available)'}",
            f"- Agent stdout: {self.agent_stdout or '(not available)'}",
            f"- Agent stderr: {self.agent_stderr or '(not available)'}",
            f"- Tests stdout: {self.tests_stdout or '(not available)'}",
            f"- Tests stderr: {self.tests_stderr or '(not available)'}",
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


def _snapshot_name(
    run_id: str,
    *,
    attempt: int,
    retry: int,
    call_role: str,
) -> str:
    safe_call_role = call_role.replace(".", "-")
    return f"{run_id}-attempt-{attempt:03d}-retry-{retry:02d}-{safe_call_role}.md"


def _yaml_lines(fields: dict[str, object]) -> list[str]:
    return [f"{key}: {_yaml_scalar(value)}" for key, value in fields.items()]


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(content)
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        raise


def _front_matter_lines(
    *,
    project_uuid: str,
    repo_root: Path,
    artifacts: RunArtifacts,
    attempt: int,
    retry: int,
    validation_command: str,
    record: DecisionRecord,
    artifact_paths: SnapshotArtifactPaths,
) -> list[str]:
    fields: dict[str, object] = {
        "schema_version": 1,
        "project_uuid": project_uuid,
        "repo_root": str(repo_root),
        "run_id": artifacts.run_id,
        "target": record.target,
        "attempt": attempt,
        "retry": retry,
        "call_role": record.call_role,
        "phase_reached": record.phase_reached,
        "decision": record.decision,
        "retry_recommendation": record.retry_recommendation,
        "failure_kind": record.failure_kind,
        "summary": record.summary,
        "validation_command": validation_command,
        "artifact_root": str(artifacts.root),
    }
    fields.update(artifact_paths.front_matter_fields())
    return _yaml_lines(fields)


def _snapshot_body_lines(
    record: DecisionRecord,
    artifacts: RunArtifacts,
    artifact_paths: SnapshotArtifactPaths,
) -> list[str]:
    return [
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
        *artifact_paths.evidence_lines(),
        "",
    ]


def _snapshot_content(
    *,
    project_uuid: str,
    repo_root: Path,
    artifacts: RunArtifacts,
    attempt: int,
    retry: int,
    validation_command: str,
    record: DecisionRecord,
    artifact_paths: SnapshotArtifactPaths,
) -> str:
    return "\n".join([
        "---",
        *_front_matter_lines(
            project_uuid=project_uuid,
            repo_root=repo_root,
            artifacts=artifacts,
            attempt=attempt,
            retry=retry,
            validation_command=validation_command,
            record=record,
            artifact_paths=artifact_paths,
        ),
        "---",
        "",
        *_snapshot_body_lines(record, artifacts, artifact_paths),
    ])


def write(
    repo_root: Path,
    artifacts: RunArtifacts,
    *,
    attempt: int,
    retry: int,
    validation_command: str,
    record: DecisionRecord,
) -> Path:
    snapshot_dir = failure_snapshots_dir(repo_root)
    snapshot_path = snapshot_dir / _snapshot_name(
        artifacts.run_id,
        attempt=attempt,
        retry=retry,
        call_role=record.call_role,
    )
    project_uuid = snapshot_dir.parent.name
    artifact_paths = SnapshotArtifactPaths.from_record(record, artifacts.root)
    content = _snapshot_content(
        project_uuid=project_uuid,
        repo_root=repo_root,
        artifacts=artifacts,
        attempt=attempt,
        retry=retry,
        validation_command=validation_command,
        record=record,
        artifact_paths=artifact_paths,
    )
    _write_text_atomic(snapshot_path, content)
    return snapshot_path


def _next_step_text(record: DecisionRecord) -> str:
    planning_step = _planning_step(record)
    if planning_step is not None:
        return (
            f"Rerun planning step `{planning_step}` from the last published "
            ".planning/state.json; failed current-step output and partial "
            "work are artifact evidence only, not resume input."
        )
    if record.decision == "retry":
        focus = f" Focus: {record.next_retry_focus}" if record.next_retry_focus else ""
        return f"Retry the same target on the next attempt.{focus}"
    if record.decision == "abandon":
        return "Abandon this target and move on to a different target."
    if record.decision == "blocked":
        return "Pause for human review before attempting more automated work."
    return "Commit the validated result and continue normally."


def _planning_step(record: DecisionRecord) -> str | None:
    if record.failure_kind != "planning-step-failed":
        return None
    prefix = "planning."
    if not record.call_role.startswith(prefix):
        return None
    step = record.call_role.removeprefix(prefix)
    return step or None


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


def _update_attempt_from_record(
    artifacts: RunArtifacts,
    *,
    attempt: int,
    retry: int,
    record: DecisionRecord,
    reason_doc_path: Path | None,
) -> None:
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
        reason_doc_path=reason_doc_path,
    )


def _log_transition_from_record(
    artifacts: RunArtifacts,
    *,
    attempt: int,
    retry: int,
    record: DecisionRecord,
    reason_doc_path: Path | None,
) -> None:
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
        reason_doc_path=reason_doc_path,
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
        _update_attempt_from_record(
            artifacts,
            attempt=attempt,
            retry=retry,
            record=record,
            reason_doc_path=None,
        )
        return None

    reason_doc = write(
        repo_root,
        artifacts,
        attempt=attempt,
        retry=retry,
        validation_command=validation_command,
        record=record,
    )
    planning_step = _planning_step(record)
    log_fields: dict[str, object] = {}
    if planning_step is not None:
        log_fields["planning_step"] = planning_step
    artifacts.log(
        "WARN",
        f"failure snapshot written: {reason_doc}",
        event=(
            "planning_step_failure_doc_written"
            if planning_step is not None
            else "failure_doc_written"
        ),
        attempt=attempt,
        retry=retry,
        target=record.target,
        call_role=record.call_role,
        phase_reached=record.phase_reached,
        reason_doc_path=str(reason_doc),
        **log_fields,
    )
    _log_transition_from_record(
        artifacts,
        attempt=attempt,
        retry=retry,
        record=record,
        reason_doc_path=reason_doc,
    )
    return reason_doc
