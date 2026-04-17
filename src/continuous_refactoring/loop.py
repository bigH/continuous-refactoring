from __future__ import annotations

import json
import random
import re
import sys
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import argparse

    from continuous_refactoring.artifacts import RunArtifacts
    from continuous_refactoring.migrations import MigrationManifest

__all__ = [
    "run_baseline_checks",
    "run_loop",
    "run_once",
]

from continuous_refactoring.artifacts import (
    CommandCapture,
    ContinuousRefactorError,
    create_run_artifacts,
)
from continuous_refactoring.agent import (
    maybe_run_agent,
    run_tests,
    summarize_output,
)
from continuous_refactoring.config import (
    failure_snapshots_dir,
    load_taste,
    reason_for_failure_path,
    register_project,
    resolve_live_migrations_dir,
    resolve_project,
)
from continuous_refactoring.git import (
    checkout_branch,
    current_branch,
    detect_main_branch,
    discard_workspace_changes,
    generate_run_branch_name,
    generate_run_once_branch_name,
    get_head_sha,
    git_commit,
    git_push,
    prepare_phase_branch,
    prepare_run_branch,
    repo_change_count,
    require_clean_worktree,
    revert_to,
    run_command,
)
from continuous_refactoring.migrations import (
    bump_last_touch,
    eligible_now,
    has_executable_phase,
    load_manifest,
    save_manifest,
)
from continuous_refactoring.phases import (
    check_phase_ready,
    execute_phase,
    generate_phase_branch_name,
)
from continuous_refactoring.planning import run_planning
from continuous_refactoring.prompts import (
    CONTINUOUS_REFACTORING_STATUS_BEGIN,
    CONTINUOUS_REFACTORING_STATUS_END,
    DEFAULT_FIX_AMENDMENT,
    DEFAULT_REFACTORING_PROMPT,
    compose_full_prompt,
    prompt_file_text,
)
from continuous_refactoring.routing import classify_target
from continuous_refactoring.scope_expansion import (
    build_scope_candidates,
    describe_scope_candidate,
    scope_candidate_to_target,
    scope_expansion_bypass_reason,
    select_scope_candidate,
    write_scope_expansion_artifacts,
)
from continuous_refactoring.targeting import Target, resolve_targets


def run_baseline_checks(
    test_command: str,
    repo_root: Path,
    *,
    stdout_path: Path,
    stderr_path: Path,
) -> tuple[bool, str]:
    result = run_tests(
        test_command,
        repo_root,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
    if result.returncode == 0:
        return True, ""
    return False, summarize_output(result)


def _load_taste_safe(repo_root: Path) -> str:
    try:
        project = resolve_project(repo_root)
        return load_taste(project)
    except ContinuousRefactorError:
        return load_taste(None)


def _resolve_live_migrations_dir(repo_root: Path) -> Path | None:
    try:
        project = resolve_project(repo_root)
    except ContinuousRefactorError:
        return None
    return resolve_live_migrations_dir(project)


def _migration_name_from_target(target: Target) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", target.description.lower()).strip("-")
    ts = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")
    prefix = slug[:40] if slug else "migration"
    return f"{prefix}-{ts}"


RunnerDecision = Literal["commit", "retry", "abandon", "blocked"]
RetryRecommendation = Literal["same-target", "new-target", "none", "human-review"]
RouteOutcome = Literal["not-routed", "commit", "abandon", "blocked"]


@dataclass(frozen=True)
class AgentStatus:
    phase_reached: str | None = None
    decision: RunnerDecision | None = None
    retry_recommendation: RetryRecommendation | None = None
    failure_kind: str | None = None
    summary: str | None = None
    next_retry_focus: str | None = None
    tests_run: str | None = None
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionRecord:
    decision: RunnerDecision
    retry_recommendation: RetryRecommendation
    target: str
    call_role: str
    phase_reached: str
    failure_kind: str
    summary: str
    next_retry_focus: str | None = None
    agent_last_message_path: Path | None = None
    agent_stdout_path: Path | None = None
    agent_stderr_path: Path | None = None
    tests_stdout_path: Path | None = None
    tests_stderr_path: Path | None = None


@dataclass(frozen=True)
class RouteResult:
    outcome: RouteOutcome
    target: Target
    planning_context: str = ""
    decision_record: DecisionRecord | None = None


def _status_path_text(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _parse_agent_status_block(text: str | None) -> AgentStatus | None:
    if not text:
        return None
    begin = text.rfind(CONTINUOUS_REFACTORING_STATUS_BEGIN)
    if begin < 0:
        return None
    end = text.find(CONTINUOUS_REFACTORING_STATUS_END, begin)
    if end < 0:
        return None
    block = text[begin + len(CONTINUOUS_REFACTORING_STATUS_BEGIN):end].strip()
    if not block:
        return None

    data: dict[str, str] = {}
    evidence: list[str] = []
    current_key: str | None = None
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if current_key == "evidence" and line.startswith("- "):
            evidence.append(line[2:].strip())
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        current_key = key.strip()
        if current_key == "evidence":
            if value.strip():
                evidence.append(value.strip())
            continue
        data[current_key] = value.strip()

    decision = data.get("decision", "").lower() or None
    if decision not in {"commit", "retry", "abandon", "blocked", None}:
        decision = None
    retry_recommendation = data.get("retry_recommendation", "").lower() or None
    if retry_recommendation not in {
        "same-target",
        "new-target",
        "none",
        "human-review",
        None,
    }:
        retry_recommendation = None

    return AgentStatus(
        phase_reached=data.get("phase_reached") or None,
        decision=decision,
        retry_recommendation=retry_recommendation,
        failure_kind=data.get("failure_kind") or None,
        summary=data.get("summary") or None,
        next_retry_focus=data.get("next_retry_focus") or None,
        tests_run=data.get("tests_run") or None,
        evidence=tuple(evidence),
    )


def _read_agent_status(
    agent: str,
    *,
    last_message_path: Path | None,
    fallback_text: str | None,
) -> AgentStatus | None:
    if agent == "codex":
        status = _parse_agent_status_block(_status_path_text(last_message_path))
        if status is not None:
            return status
    return _parse_agent_status_block(fallback_text)


def _sanitize_text(text: str | None, repo_root: Path) -> str | None:
    if not text:
        return None
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "codex exec" in line:
            continue
        line = line.replace(str(repo_root), "<repo>")
        line = re.sub(r"/tmp/[^ ]+", "<tmp>", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    if not lines:
        return None
    return " ".join(lines)[:240]


def _capture_highlight(capture: CommandCapture | None, repo_root: Path) -> str | None:
    if capture is None:
        return None
    text = "\n".join([capture.stdout, capture.stderr])
    for line in reversed(text.splitlines()):
        sanitized = _sanitize_text(line, repo_root)
        if sanitized:
            return sanitized
    return None


def _relative_path(path: Path | None, root: Path) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _status_summary(
    status: AgentStatus | None,
    *,
    fallback: str,
    repo_root: Path,
) -> tuple[str, str | None]:
    summary = _sanitize_text(status.summary if status else None, repo_root) or fallback
    focus = _sanitize_text(status.next_retry_focus if status else None, repo_root)
    return summary, focus


def _make_decision_record(
    *,
    decision: RunnerDecision,
    retry_recommendation: RetryRecommendation,
    target: str,
    call_role: str,
    phase_reached: str,
    failure_kind: str,
    summary: str,
    next_retry_focus: str | None = None,
    agent_last_message_path: Path | None = None,
    agent_stdout_path: Path | None = None,
    agent_stderr_path: Path | None = None,
    tests_stdout_path: Path | None = None,
    tests_stderr_path: Path | None = None,
) -> DecisionRecord:
    return DecisionRecord(
        decision=decision,
        retry_recommendation=retry_recommendation,
        target=target,
        call_role=call_role,
        phase_reached=phase_reached,
        failure_kind=failure_kind,
        summary=summary,
        next_retry_focus=next_retry_focus,
        agent_last_message_path=agent_last_message_path,
        agent_stdout_path=agent_stdout_path,
        agent_stderr_path=agent_stderr_path,
        tests_stdout_path=tests_stdout_path,
        tests_stderr_path=tests_stderr_path,
    )


def _error_failure_kind(message: str) -> str:
    lowered = message.lower()
    if "timed out" in lowered:
        return "timeout"
    if "produced no output" in lowered:
        return "stuck"
    return "agent-infra-failure"


def _retry_context(record: DecisionRecord) -> str:
    lines = [
        f"- Previous attempt on `{record.target}` failed during `{record.call_role}`.",
        f"- Summary: {record.summary}",
    ]
    if record.next_retry_focus:
        lines.append(f"- Next retry focus: {record.next_retry_focus}")
    return "\n".join(lines)


def _yaml_scalar(value: object) -> str:
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value))


def _write_reason_for_failure(
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
    latest_path = reason_for_failure_path(repo_root)
    snapshot_dir = failure_snapshots_dir(repo_root)
    snapshot_name = (
        f"{artifacts.run_id}-attempt-{attempt:03d}-retry-{retry:02d}-"
        f"{record.call_role.replace('.', '-')}.md"
    )
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
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(content, encoding="utf-8")
    (snapshot_dir / snapshot_name).write_text(content, encoding="utf-8")
    return latest_path


def _next_step_text(record: DecisionRecord) -> str:
    if record.decision == "retry":
        focus = f" Focus: {record.next_retry_focus}" if record.next_retry_focus else ""
        return f"Retry the same target on the next attempt.{focus}"
    if record.decision == "abandon":
        return "Abandon this target and move on to a different target."
    if record.decision == "blocked":
        return "Pause for human review before attempting more automated work."
    return "Commit the validated result and continue normally."


def _effective_record(
    record: DecisionRecord,
    *,
    retry: int,
    max_attempts: int | None,
) -> DecisionRecord:
    if record.decision != "retry" or record.retry_recommendation != "same-target":
        return record
    if max_attempts is None or retry < max_attempts:
        return record
    summary = f"Exhausted {max_attempts} attempts. Last failure: {record.summary}"
    return _make_decision_record(
        decision="abandon",
        retry_recommendation="new-target",
        target=record.target,
        call_role=record.call_role,
        phase_reached=record.phase_reached,
        failure_kind=record.failure_kind,
        summary=summary,
        next_retry_focus=record.next_retry_focus,
        agent_last_message_path=record.agent_last_message_path,
        agent_stdout_path=record.agent_stdout_path,
        agent_stderr_path=record.agent_stderr_path,
        tests_stdout_path=record.tests_stdout_path,
        tests_stderr_path=record.tests_stderr_path,
    )


def _persist_decision(
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

    reason_doc = _write_reason_for_failure(
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
        f"reason-for-failure written: {reason_doc}",
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


def _default_retry_recommendation(
    decision: RunnerDecision,
) -> RetryRecommendation:
    if decision == "retry":
        return "same-target"
    if decision == "abandon":
        return "new-target"
    if decision == "blocked":
        return "human-review"
    return "none"


def _run_refactor_attempt(
    *,
    repo_root: Path,
    artifacts: RunArtifacts,
    target: Target,
    attempt: int,
    retry: int,
    agent: str,
    model: str,
    effort: str,
    prompt: str,
    timeout: int | None,
    validation_command: str,
    show_agent_logs: bool,
    show_command_logs: bool,
    commit_message_prefix: str,
    branch_name: str,
    no_push: bool,
    push_remote: str,
) -> DecisionRecord:
    discard_workspace_changes(repo_root)
    head_before = get_head_sha(repo_root)

    if retry > 1:
        print(f"  retry {retry}")

    attempt_dir = artifacts.attempt_dir(attempt, retry=retry) / "refactor"
    last_message_path = (
        attempt_dir / "agent-last-message.md" if agent == "codex" else None
    )
    agent_stdout = attempt_dir / "agent.stdout.log"
    agent_stderr = attempt_dir / "agent.stderr.log"
    tests_stdout = attempt_dir / "tests.stdout.log"
    tests_stderr = attempt_dir / "tests.stderr.log"
    call_role = "refactor"
    phase_reached = "refactor"

    artifacts.log_call_started(
        attempt=attempt,
        retry=retry,
        target=target.description,
        call_role=call_role,
    )
    try:
        agent_result = maybe_run_agent(
            agent=agent,
            model=model,
            effort=effort,
            prompt=prompt,
            repo_root=repo_root,
            stdout_path=agent_stdout,
            stderr_path=agent_stderr,
            last_message_path=last_message_path,
            mirror_to_terminal=show_agent_logs,
            timeout=timeout,
        )
    except ContinuousRefactorError as error:
        artifacts.log_call_finished(
            attempt=attempt,
            retry=retry,
            target=target.description,
            call_role=call_role,
            status="failed",
            level="WARN",
            summary=str(error),
        )
        revert_to(repo_root, head_before)
        agent_status = _read_agent_status(
            agent,
            last_message_path=last_message_path,
            fallback_text=None,
        )
        summary, focus = _status_summary(
            agent_status,
            fallback=_sanitize_text(str(error), repo_root) or str(error),
            repo_root=repo_root,
        )
        return _make_decision_record(
            decision="retry",
            retry_recommendation="same-target",
            target=target.description,
            call_role=call_role,
            phase_reached=agent_status.phase_reached or phase_reached if agent_status else phase_reached,
            failure_kind=_error_failure_kind(str(error)),
            summary=summary,
            next_retry_focus=focus,
            agent_last_message_path=last_message_path,
            agent_stdout_path=agent_stdout,
            agent_stderr_path=agent_stderr,
        )

    agent_status = _read_agent_status(
        agent,
        last_message_path=last_message_path,
        fallback_text=agent_result.stdout,
    )
    if agent_result.returncode != 0:
        summary, focus = _status_summary(
            agent_status,
            fallback=f"{agent} exited with code {agent_result.returncode}",
            repo_root=repo_root,
        )
        artifacts.log_call_finished(
            attempt=attempt,
            retry=retry,
            target=target.description,
            call_role=call_role,
            status="failed",
            level="WARN",
            returncode=agent_result.returncode,
            summary=summary,
        )
        revert_to(repo_root, head_before)
        return _make_decision_record(
            decision="retry",
            retry_recommendation="same-target",
            target=target.description,
            call_role=call_role,
            phase_reached=agent_status.phase_reached or phase_reached if agent_status else phase_reached,
            failure_kind="agent-exited-nonzero",
            summary=summary,
            next_retry_focus=focus,
            agent_last_message_path=last_message_path,
            agent_stdout_path=agent_result.stdout_path,
            agent_stderr_path=agent_result.stderr_path,
        )

    artifacts.log_call_finished(
        attempt=attempt,
        retry=retry,
        target=target.description,
        call_role=call_role,
        status="finished",
        returncode=agent_result.returncode,
    )

    validation_role = "validation"
    artifacts.log_call_started(
        attempt=attempt,
        retry=retry,
        target=target.description,
        call_role=validation_role,
        phase_reached=agent_status.phase_reached or phase_reached if agent_status else phase_reached,
    )
    try:
        validation_result = run_tests(
            validation_command,
            repo_root,
            stdout_path=tests_stdout,
            stderr_path=tests_stderr,
            mirror_to_terminal=show_command_logs,
        )
    except ContinuousRefactorError as error:
        artifacts.log_call_finished(
            attempt=attempt,
            retry=retry,
            target=target.description,
            call_role=validation_role,
            phase_reached=agent_status.phase_reached or phase_reached if agent_status else phase_reached,
            status="failed",
            level="WARN",
            summary=str(error),
        )
        revert_to(repo_root, head_before)
        summary, focus = _status_summary(
            agent_status,
            fallback=_sanitize_text(str(error), repo_root) or str(error),
            repo_root=repo_root,
        )
        return _make_decision_record(
            decision="retry",
            retry_recommendation="same-target",
            target=target.description,
            call_role=validation_role,
            phase_reached=agent_status.phase_reached or phase_reached if agent_status else phase_reached,
            failure_kind="validation-infra-failure",
            summary=summary,
            next_retry_focus=focus,
            agent_last_message_path=last_message_path,
            agent_stdout_path=agent_result.stdout_path,
            agent_stderr_path=agent_result.stderr_path,
            tests_stdout_path=tests_stdout,
            tests_stderr_path=tests_stderr,
        )

    if validation_result.returncode != 0:
        summary, focus = _status_summary(
            agent_status,
            fallback="validation failed after refactor",
            repo_root=repo_root,
        )
        artifacts.log_call_finished(
            attempt=attempt,
            retry=retry,
            target=target.description,
            call_role=validation_role,
            phase_reached=agent_status.phase_reached or phase_reached if agent_status else phase_reached,
            status="failed",
            level="WARN",
            returncode=validation_result.returncode,
            summary=summary,
        )
        revert_to(repo_root, head_before)
        return _make_decision_record(
            decision="retry",
            retry_recommendation="same-target",
            target=target.description,
            call_role=validation_role,
            phase_reached=agent_status.phase_reached or phase_reached if agent_status else phase_reached,
            failure_kind="validation-failed",
            summary=summary,
            next_retry_focus=focus,
            agent_last_message_path=last_message_path,
            agent_stdout_path=agent_result.stdout_path,
            agent_stderr_path=agent_result.stderr_path,
            tests_stdout_path=validation_result.stdout_path,
            tests_stderr_path=validation_result.stderr_path,
        )

    artifacts.log_call_finished(
        attempt=attempt,
        retry=retry,
        target=target.description,
        call_role=validation_role,
        phase_reached=agent_status.phase_reached or phase_reached if agent_status else phase_reached,
        status="finished",
        returncode=validation_result.returncode,
    )

    if agent_status and agent_status.decision in {"retry", "abandon", "blocked"}:
        revert_to(repo_root, head_before)
        summary, focus = _status_summary(
            agent_status,
            fallback=f"agent requested {agent_status.decision}",
            repo_root=repo_root,
        )
        decision = agent_status.decision
        retry_recommendation = (
            agent_status.retry_recommendation
            or _default_retry_recommendation(decision)
        )
        return _make_decision_record(
            decision=decision,
            retry_recommendation=retry_recommendation,
            target=target.description,
            call_role=call_role,
            phase_reached=agent_status.phase_reached or phase_reached,
            failure_kind=agent_status.failure_kind or "agent-requested-transition",
            summary=summary,
            next_retry_focus=focus,
            agent_last_message_path=last_message_path,
            agent_stdout_path=agent_result.stdout_path,
            agent_stderr_path=agent_result.stderr_path,
            tests_stdout_path=validation_result.stdout_path,
            tests_stderr_path=validation_result.stderr_path,
        )

    commit = _finalize_commit(
        repo_root,
        head_before,
        f"{commit_message_prefix}: {target.description}",
        artifacts=artifacts,
        attempt=attempt,
        phase="refactor",
    )
    if commit is not None and not no_push:
        git_push(repo_root, push_remote, branch_name)
        artifacts.record_push(attempt)

    return _make_decision_record(
        decision="commit",
        retry_recommendation="none",
        target=target.description,
        call_role=validation_role,
        phase_reached=agent_status.phase_reached or phase_reached if agent_status else phase_reached,
        failure_kind="none",
        summary="Validated refactor ready to commit",
        agent_last_message_path=last_message_path,
        agent_stdout_path=agent_result.stdout_path,
        agent_stderr_path=agent_result.stderr_path,
        tests_stdout_path=validation_result.stdout_path,
        tests_stderr_path=validation_result.stderr_path,
    )


def _enumerate_eligible_manifests(
    live_dir: Path, now: datetime,
) -> list[tuple[MigrationManifest, Path]]:
    if not live_dir.is_dir():
        return []
    candidates: list[tuple[MigrationManifest, Path]] = []
    for entry in sorted(live_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("__"):
            continue
        manifest_path = entry / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = load_manifest(manifest_path)
        if manifest.status not in ("ready", "in-progress"):
            continue
        if not has_executable_phase(manifest):
            continue
        if not eligible_now(manifest, now):
            continue
        candidates.append((manifest, manifest_path))
    candidates.sort(key=lambda pair: datetime.fromisoformat(pair[0].created_at))
    return candidates


def _try_migration_tick(
    live_dir: Path,
    taste: str,
    repo_root: Path,
    artifacts: RunArtifacts,
    *,
    agent: str,
    model: str,
    effort: str,
    timeout: int | None,
    commit_message_prefix: str,
    attempt: int,
) -> tuple[RouteOutcome, DecisionRecord | None]:
    now = datetime.now(timezone.utc)
    candidates = _enumerate_eligible_manifests(live_dir, now)

    for manifest, manifest_path in candidates:
        phase = manifest.phases[manifest.current_phase]
        target_label = f"{manifest.name} phase-{manifest.current_phase}/{phase.name}"
        try:
            verdict, reason = check_phase_ready(
                phase,
                manifest,
                repo_root,
                artifacts,
                attempt=attempt,
                retry=1,
                agent=agent,
                model=model,
                effort=effort,
                timeout=timeout,
            )
        except ContinuousRefactorError as error:
            summary = _sanitize_text(str(error), repo_root) or str(error)
            return (
                "abandon",
                _make_decision_record(
                    decision="abandon",
                    retry_recommendation="new-target",
                    target=target_label,
                    call_role="phase.ready-check",
                    phase_reached="phase.ready-check",
                    failure_kind=_error_failure_kind(str(error)),
                    summary=summary,
                ),
            )

        if verdict == "yes":
            phase_branch = generate_phase_branch_name(
                manifest.name, manifest.current_phase, phase.name,
            )
            saved_branch = current_branch(repo_root)
            prepare_phase_branch(repo_root, phase_branch)
            head_before = get_head_sha(repo_root)

            outcome = execute_phase(
                phase,
                manifest,
                taste,
                repo_root,
                live_dir,
                artifacts,
                attempt=attempt,
                retry=1,
                agent=agent,
                model=model,
                effort=effort,
                timeout=timeout,
            )

            if outcome.status != "failed":
                _finalize_commit(
                    repo_root,
                    head_before,
                    f"{commit_message_prefix}: migration/{manifest.name}"
                    f"/phase-{manifest.current_phase}/{phase.name}",
                    artifacts=artifacts,
                    attempt=attempt,
                    phase="migration",
                )

            checkout_branch(repo_root, saved_branch)

            print(
                f"Migration: {outcome.status}"
                f" — {manifest.name} phase-{manifest.current_phase}/{phase.name}"
            )
            if outcome.status == "failed":
                return (
                    "abandon",
                    _make_decision_record(
                        decision="abandon",
                        retry_recommendation="new-target",
                        target=target_label,
                        call_role=outcome.call_role or "phase.execute",
                        phase_reached=outcome.phase_reached or "phase.execute",
                        failure_kind=outcome.failure_kind or "phase-failed",
                        summary=_sanitize_text(outcome.reason, repo_root) or outcome.reason,
                    ),
                )
            return (
                "commit",
                _make_decision_record(
                    decision="commit",
                    retry_recommendation="none",
                    target=target_label,
                    call_role="phase.execute",
                    phase_reached="phase.execute",
                    failure_kind="none",
                    summary="Migration phase completed successfully",
                ),
            )

        updated = bump_last_touch(manifest, now)
        if updated.wake_up_on is None:
            wake = (now + timedelta(days=7)).isoformat(timespec="milliseconds")
            updated = replace(updated, wake_up_on=wake)
        if verdict == "unverifiable":
            updated = replace(updated, awaiting_human_review=True)
        save_manifest(updated, manifest_path)
        if verdict == "unverifiable":
            summary = _sanitize_text(reason, repo_root) or "Phase requires human review"
            return (
                "blocked",
                _make_decision_record(
                    decision="blocked",
                    retry_recommendation="human-review",
                    target=target_label,
                    call_role="phase.ready-check",
                    phase_reached="phase.ready-check",
                    failure_kind="phase-ready-unverifiable",
                    summary=summary,
                ),
            )

    return "not-routed", None


def _scope_bypass_context(target: Target, reason: str) -> str:
    lines = [
        f"Scope expansion bypassed: {reason}",
        "Files:",
        *(f"- {file_path}" for file_path in target.files),
    ]
    return "\n".join(lines)


def _expand_target_for_classification(
    target: Target,
    taste: str,
    repo_root: Path,
    artifacts: RunArtifacts,
    *,
    agent: str,
    model: str,
    effort: str,
    timeout: int | None,
) -> tuple[Target, str]:
    scope_dir = artifacts.root / "scope-expansion"
    bypass_reason = scope_expansion_bypass_reason(target)
    if bypass_reason is not None:
        write_scope_expansion_artifacts(
            scope_dir,
            target,
            (),
            bypass_reason=bypass_reason,
        )
        bypass_line = f"selected-candidate: seed — {bypass_reason}\n"
        (scope_dir / "selection.stdout.log").write_text(bypass_line, encoding="utf-8")
        (scope_dir / "selection-last-message.md").write_text(
            bypass_line,
            encoding="utf-8",
        )
        return target, _scope_bypass_context(target, bypass_reason)

    candidates = build_scope_candidates(target, repo_root)
    selection = select_scope_candidate(
        target,
        candidates,
        taste,
        repo_root,
        artifacts,
        agent=agent,
        model=model,
        effort=effort,
        timeout=timeout,
    )
    write_scope_expansion_artifacts(
        scope_dir,
        target,
        candidates,
        selection=selection,
    )

    selected_candidate = next(
        candidate for candidate in candidates if candidate.kind == selection.kind
    )
    planning_context = describe_scope_candidate(selected_candidate)
    return scope_candidate_to_target(target, selected_candidate), planning_context


def _route_and_run(
    target: Target,
    taste: str,
    repo_root: Path,
    artifacts: RunArtifacts,
    *,
    agent: str,
    model: str,
    effort: str,
    timeout: int | None,
    commit_message_prefix: str,
    attempt: int,
) -> RouteResult:
    live_dir = _resolve_live_migrations_dir(repo_root)
    if live_dir is None:
        return RouteResult(outcome="not-routed", target=target)

    migration_result, migration_record = _try_migration_tick(
        live_dir, taste, repo_root, artifacts,
        agent=agent, model=model, effort=effort,
        timeout=timeout, commit_message_prefix=commit_message_prefix,
        attempt=attempt,
    )
    if migration_result != "not-routed":
        return RouteResult(
            outcome=migration_result,
            target=target,
            decision_record=migration_record,
        )

    target, planning_context = _expand_target_for_classification(
        target,
        taste,
        repo_root,
        artifacts,
        agent=agent,
        model=model,
        effort=effort,
        timeout=timeout,
    )

    try:
        decision = classify_target(
            target,
            taste,
            repo_root,
            artifacts,
            attempt=attempt,
            retry=1,
            agent=agent,
            model=model,
            effort=effort,
            timeout=timeout,
        )
    except ContinuousRefactorError as error:
        summary = _sanitize_text(str(error), repo_root) or str(error)
        return RouteResult(
            outcome="abandon",
            target=target,
            planning_context=planning_context,
            decision_record=_make_decision_record(
                decision="abandon",
                retry_recommendation="new-target",
                target=target.description,
                call_role="classify",
                phase_reached="classify",
                failure_kind=_error_failure_kind(str(error)),
                summary=summary,
            ),
        )
    print(f"Classification: {decision} — {target.description}")

    if decision == "cohesive-cleanup":
        return RouteResult(
            outcome="not-routed",
            target=target,
            planning_context=planning_context,
        )

    migration_name = _migration_name_from_target(target)
    head_before = get_head_sha(repo_root)
    try:
        outcome = run_planning(
            migration_name,
            target.description,
            taste,
            repo_root,
            live_dir,
            artifacts,
            attempt=attempt,
            retry=1,
            agent=agent,
            model=model,
            effort=effort,
            timeout=timeout,
            extra_context=planning_context,
        )
    except ContinuousRefactorError as error:
        summary = _sanitize_text(str(error), repo_root) or str(error)
        call_role = "planning.final-review"
        match = re.match(r"^(planning\.[a-z0-9-]+)\s+failed:", str(error))
        if match:
            call_role = match.group(1)
        return RouteResult(
            outcome="abandon",
            target=target,
            planning_context=planning_context,
            decision_record=_make_decision_record(
                decision="abandon",
                retry_recommendation="new-target",
                target=target.description,
                call_role=call_role,
                phase_reached=call_role,
                failure_kind=_error_failure_kind(str(error)),
                summary=summary,
            ),
        )

    _finalize_commit(
        repo_root,
        head_before,
        f"{commit_message_prefix}: plan {migration_name}",
        artifacts=artifacts,
        attempt=attempt,
        phase="planning",
    )

    print(f"Planning: {_describe_planning_outcome(outcome.status)} — {outcome.reason}")
    if outcome.status == "skipped":
        return RouteResult(
            outcome="abandon",
            target=target,
            planning_context=planning_context,
            decision_record=_make_decision_record(
                decision="abandon",
                retry_recommendation="new-target",
                target=target.description,
                call_role="planning.final-review",
                phase_reached="planning.final-review",
                failure_kind="planning-rejected",
                summary=_sanitize_text(outcome.reason, repo_root) or outcome.reason,
            ),
        )
    return RouteResult(
        outcome="commit",
        target=target,
        planning_context=planning_context,
        decision_record=_make_decision_record(
            decision="commit",
            retry_recommendation="none",
            target=target.description,
            call_role="planning.final-review",
            phase_reached="planning.final-review",
            failure_kind="none",
            summary=_sanitize_text(outcome.reason, repo_root) or outcome.reason,
        ),
    )


def _describe_planning_outcome(status: str) -> str:
    if status == "ready":
        return "queued for execution"
    if status == "awaiting_human_review":
        return "awaiting human review"
    return status.replace("_", " ")


def _resolve_base_prompt(args: argparse.Namespace) -> str:
    if args.refactoring_prompt:
        return prompt_file_text(args.refactoring_prompt)
    return DEFAULT_REFACTORING_PROMPT


def _build_target_fallback(scope_instruction: str | None) -> Target:
    return Target(
        description="general refactoring",
        files=(),
        scoping=scope_instruction,
        model_override=None,
        effort_override=None,
        provenance="fallback",
    )


def _effective_max_attempts(raw: int | None) -> int | None:
    """Normalize --max-attempts: None -> 1, 0 -> None (unlimited), N -> N."""
    if raw is None:
        return 1
    if raw == 0:
        return None
    return raw


def _resolve_fix_amendment_text(args: argparse.Namespace) -> str:
    if args.fix_prompt:
        return prompt_file_text(args.fix_prompt)
    return DEFAULT_FIX_AMENDMENT


def _parse_paths_arg(raw_paths: str | None) -> tuple[str, ...] | None:
    if not raw_paths:
        return None
    parsed = tuple(path.strip() for path in raw_paths.split(":") if path.strip())
    return parsed or None


def _resolve_targets_from_args(
    args: argparse.Namespace,
    repo_root: Path,
) -> list[Target]:
    return resolve_targets(
        extensions=args.extensions,
        globs=args.globs,
        targets_path=args.targets,
        paths=_parse_paths_arg(args.paths),
        repo_root=repo_root,
    )


def _max_attempts_exhausted(
    target: Target,
    retry: int,
    max_attempts: int | None,
    *,
    artifacts: RunArtifacts,
    target_index: int,
) -> bool:
    if max_attempts is None or retry < max_attempts:
        return False
    artifacts.log(
        "WARN",
        f"Exhausted {max_attempts} attempts: {target.description}",
        event="max_attempts_exhausted",
        attempt=target_index,
        retry=retry,
    )
    return True


def _sleep_between_targets(
    sleep_seconds: float,
    *,
    artifacts: RunArtifacts,
    target_index: int,
    total_targets: int,
) -> None:
    if sleep_seconds <= 0 or target_index >= total_targets:
        return
    artifacts.log(
        "INFO",
        f"Sleeping {sleep_seconds:g}s before next target",
        event="sleep_between_targets",
        attempt=target_index,
        sleep_seconds=sleep_seconds,
    )
    print(f"Sleeping {sleep_seconds:g}s before next target")
    time.sleep(sleep_seconds)


def _finalize_commit(
    repo_root: Path,
    head_before: str,
    commit_message: str,
    *,
    artifacts: RunArtifacts,
    attempt: int,
    phase: str,
) -> str | None:
    head_after = get_head_sha(repo_root)
    if head_after == head_before and repo_change_count(repo_root) == 0:
        return None

    # The runner owns the final commit. If an agent already committed, squash it
    # back into a single driver commit so logs and artifacts match git history.
    if head_after != head_before:
        run_command(["git", "reset", "--soft", head_before], cwd=repo_root)

    commit = git_commit(repo_root, commit_message)
    artifacts.record_commit(attempt, phase, commit)
    print(f"Committed: {commit}")
    return commit


def run_once(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    timeout = args.timeout or 900
    taste = _load_taste_safe(repo_root)

    targets = _resolve_targets_from_args(args, repo_root)
    target = (
        random.choice(targets)
        if targets
        else _build_target_fallback(args.scope_instruction)
    )

    base_prompt = _resolve_base_prompt(args)
    model = target.model_override or args.model
    effort = target.effort_override or args.effort

    artifacts = create_run_artifacts(
        repo_root,
        agent=args.agent,
        model=model,
        effort=effort,
        test_command=args.validation_command,
    )
    artifacts.log("INFO", f"run artifacts: {artifacts.root}", event="artifacts_ready")

    final_status = "running"
    error_message: str | None = None
    try:
        require_clean_worktree(repo_root)

        branch_name = prepare_run_branch(
            repo_root,
            args.use_branch,
            generate_run_once_branch_name(),
        )
        artifacts.mark_attempt_started(1)

        print(f"\n── Target: {target.description} ──")
        route_result = _route_and_run(
            target, taste, repo_root, artifacts,
            agent=args.agent, model=model, effort=effort,
            timeout=timeout,
            commit_message_prefix="continuous refactor",
            attempt=1,
        )
        target = route_result.target
        if route_result.outcome == "commit":
            final_status = "completed"
            return 0
        if route_result.outcome in {"abandon", "blocked"}:
            final_status = "migration_failed"
            raise ContinuousRefactorError(
                route_result.decision_record.summary
                if route_result.decision_record is not None
                else "Migration phase execution failed"
            )

        prompt = compose_full_prompt(
            base_prompt=base_prompt,
            taste=taste,
            target=target,
            scope_instruction=args.scope_instruction,
            validation_command=args.validation_command,
            attempt=1,
        )

        head_before = get_head_sha(repo_root)

        attempt_dir = artifacts.attempt_dir(1) / "refactor"
        last_message_path = (
            attempt_dir / "agent-last-message.md" if args.agent == "codex" else None
        )

        agent_result = maybe_run_agent(
            agent=args.agent,
            model=model,
            effort=effort,
            prompt=prompt,
            repo_root=repo_root,
            stdout_path=attempt_dir / "agent.stdout.log",
            stderr_path=attempt_dir / "agent.stderr.log",
            last_message_path=last_message_path,
            mirror_to_terminal=args.show_agent_logs,
            timeout=timeout,
        )

        if agent_result.returncode != 0:
            final_status = "agent_failed"
            raise ContinuousRefactorError(
                f"Agent failed with exit code {agent_result.returncode}"
            )

        validation_result = run_tests(
            args.validation_command,
            repo_root,
            stdout_path=attempt_dir / "tests.stdout.log",
            stderr_path=attempt_dir / "tests.stderr.log",
            mirror_to_terminal=args.show_command_logs,
        )

        if validation_result.returncode != 0:
            revert_to(repo_root, head_before)
            final_status = "validation_failed"
            raise ContinuousRefactorError("Validation failed after agent run")

        _finalize_commit(
            repo_root,
            head_before,
            "continuous refactor: run-once",
            artifacts=artifacts,
            attempt=1,
            phase="run_once",
        )

        main_branch = detect_main_branch(repo_root)
        diff_stat = run_command(
            ["git", "diff", f"{main_branch}...HEAD", "--stat"],
            cwd=repo_root,
            check=False,
        )
        print(f"Branch: {branch_name}")
        print(diff_stat.stdout)
        final_status = "completed"
        return 0

    except ContinuousRefactorError as error:
        if final_status == "running":
            final_status = "failed"
        error_message = str(error)
        raise
    except KeyboardInterrupt:
        final_status = "interrupted"
        artifacts.log("WARN", "Interrupted", event="interrupted")
        print(f"\nArtifact logs: {artifacts.root}", file=sys.stderr)
        return 130
    finally:
        artifacts.finish(final_status, error_message=error_message)


def run_loop(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    timeout = args.timeout or 1800
    sleep_seconds = getattr(args, "sleep", 0.0)
    max_consecutive = args.max_consecutive_failures
    max_attempts_effective = _effective_max_attempts(
        getattr(args, "max_attempts", None)
    )
    taste = _load_taste_safe(repo_root)

    targets = _resolve_targets_from_args(args, repo_root)
    random.shuffle(targets)

    max_refactors = args.max_refactors
    if max_refactors is None and args.targets:
        max_refactors = len(targets)
    if max_refactors and len(targets) > max_refactors:
        targets = targets[:max_refactors]

    fell_back_to_scope = False
    if not targets:
        targets = [_build_target_fallback(args.scope_instruction)]
        fell_back_to_scope = bool(args.extensions or args.globs or args.paths)

    base_prompt = _resolve_base_prompt(args)
    fix_amendment_text = _resolve_fix_amendment_text(args)

    artifacts = create_run_artifacts(
        repo_root,
        agent=args.agent,
        model=args.model,
        effort=args.effort,
        test_command=args.validation_command,
    )
    artifacts.log("INFO", f"run artifacts: {artifacts.root}", event="artifacts_ready")
    if max_attempts_effective is None:
        artifacts.log(
            "WARN",
            "max_attempts=0: unlimited retries; permanently-broken targets will not exit",
            event="max_attempts_unlimited",
        )
    if fell_back_to_scope:
        artifacts.log(
            "INFO",
            "Targeting patterns matched no tracked files; falling back to scope-instruction.",
            event="targeting_fallback",
        )

    final_status = "running"
    error_message: str | None = None
    consecutive_failures = 0
    total_targets = len(targets)

    try:
        require_clean_worktree(repo_root)

        branch_name = prepare_run_branch(
            repo_root,
            args.use_branch,
            generate_run_branch_name(),
        )

        baseline_ok, baseline_context = run_baseline_checks(
            args.validation_command,
            repo_root,
            stdout_path=artifacts.baseline_dir("initial") / "tests.stdout.log",
            stderr_path=artifacts.baseline_dir("initial") / "tests.stderr.log",
        )
        if not baseline_ok:
            final_status = "baseline_failed"
            raise ContinuousRefactorError(
                f"Baseline validation failed\n{baseline_context}"
            )

        for target_index, target in enumerate(targets, start=1):
            artifacts.mark_attempt_started(target_index)

            model = target.model_override or args.model
            effort = target.effort_override or args.effort

            print(
                f"\n── Target {target_index}/{total_targets}: {target.description} ──"
            )
            route_result = _route_and_run(
                target, taste, repo_root, artifacts,
                agent=args.agent, model=model, effort=effort,
                timeout=timeout,
                commit_message_prefix=args.commit_message_prefix,
                attempt=target_index,
            )
            target = route_result.target
            if route_result.outcome == "commit":
                if route_result.decision_record is not None:
                    _persist_decision(
                        repo_root,
                        artifacts,
                        attempt=target_index,
                        retry=1,
                        validation_command=args.validation_command,
                        record=route_result.decision_record,
                    )
                consecutive_failures = 0
                _sleep_between_targets(
                    sleep_seconds,
                    artifacts=artifacts,
                    target_index=target_index,
                    total_targets=total_targets,
                )
                continue
            if route_result.outcome in {"abandon", "blocked"}:
                if route_result.decision_record is not None:
                    _persist_decision(
                        repo_root,
                        artifacts,
                        attempt=target_index,
                        retry=1,
                        validation_command=args.validation_command,
                        record=route_result.decision_record,
                    )
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive:
                    final_status = "max_consecutive_failures"
                    raise ContinuousRefactorError(
                        f"Stopping: {max_consecutive} consecutive failures"
                    )
                _sleep_between_targets(
                    sleep_seconds,
                    artifacts=artifacts,
                    target_index=target_index,
                    total_targets=total_targets,
                )
                continue

            retry_context: str | None = None
            outcome_record: DecisionRecord | None = None
            retry = 0

            while True:
                retry += 1
                prompt = compose_full_prompt(
                    base_prompt=base_prompt,
                    taste=taste,
                    target=target,
                    scope_instruction=args.scope_instruction,
                    validation_command=args.validation_command,
                    attempt=retry,
                    retry_context=retry_context,
                    fix_amendment=fix_amendment_text if retry > 1 else None,
                )
                record = _run_refactor_attempt(
                    repo_root=repo_root,
                    artifacts=artifacts,
                    target=target,
                    attempt=target_index,
                    retry=retry,
                    agent=args.agent,
                    model=model,
                    effort=effort,
                    prompt=prompt,
                    timeout=timeout,
                    validation_command=args.validation_command,
                    show_agent_logs=args.show_agent_logs,
                    show_command_logs=args.show_command_logs,
                    commit_message_prefix=args.commit_message_prefix,
                    branch_name=branch_name,
                    no_push=args.no_push,
                    push_remote=args.push_remote,
                )
                effective_record = _effective_record(
                    record,
                    retry=retry,
                    max_attempts=max_attempts_effective,
                )
                if (
                    record.decision == "retry"
                    and effective_record.decision == "abandon"
                    and max_attempts_effective is not None
                ):
                    artifacts.log(
                        "WARN",
                        f"Exhausted {max_attempts_effective} attempts: {target.description}",
                        event="max_attempts_exhausted",
                        attempt=target_index,
                        retry=retry,
                        target=target.description,
                        call_role=record.call_role,
                    )
                _persist_decision(
                    repo_root,
                    artifacts,
                    attempt=target_index,
                    retry=retry,
                    validation_command=args.validation_command,
                    record=effective_record,
                )
                outcome_record = effective_record
                if effective_record.decision == "retry":
                    retry_context = _retry_context(effective_record)
                    continue
                break

            if outcome_record is not None and outcome_record.decision == "commit":
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive:
                    final_status = "max_consecutive_failures"
                    raise ContinuousRefactorError(
                        f"Stopping: {max_consecutive} consecutive failures"
                    )

            _sleep_between_targets(
                sleep_seconds,
                artifacts=artifacts,
                target_index=target_index,
                total_targets=total_targets,
            )

        final_status = "completed"
        return 0

    except ContinuousRefactorError as error:
        if final_status == "running":
            final_status = "failed"
        error_message = str(error)
        raise
    except KeyboardInterrupt:
        final_status = "interrupted"
        artifacts.log("WARN", "Interrupted", event="interrupted")
        discard_workspace_changes(repo_root)
        print(f"\nArtifact logs: {artifacts.root}", file=sys.stderr)
        return 130
    finally:
        artifacts.finish(final_status, error_message=error_message)
