from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from continuous_refactoring.artifacts import RunArtifacts
    from continuous_refactoring.decisions import AgentStatus
    from continuous_refactoring.migrations import MigrationManifest, PhaseSpec

__all__ = [
    "ExecutePhaseOutcome",
    "ReadyVerdict",
    "check_phase_ready",
    "execute_phase",
]

from continuous_refactoring.agent import maybe_run_agent, run_tests
from continuous_refactoring.artifacts import ContinuousRefactorError, iso_timestamp
from continuous_refactoring.commit_messages import commit_rationale
from continuous_refactoring.decisions import (
    error_failure_kind,
    read_status,
    resolved_phase_reached,
    sanitize_text,
    status_summary,
)
from continuous_refactoring.git import get_head_sha, revert_to
from continuous_refactoring.migrations import (
    complete_manifest_phase,
    migration_root,
    phase_file_reference,
    save_manifest,
)
from continuous_refactoring.prompts import (
    compose_phase_execution_prompt,
    compose_phase_ready_prompt,
)

ReadyVerdict = Literal["yes", "no", "unverifiable"]

_READY_RE = re.compile(
    r"^ready:\s*(?P<verdict>yes|no|unverifiable)\b(?P<reason>.*)$",
    re.IGNORECASE,
)
_PHASE_EXECUTE_ROLE = "phase.execute"
_PHASE_VALIDATION_ROLE = "phase.validation"
_VALIDATION_FAILED_SUMMARY = "validation failed after phase execution"


@dataclass(frozen=True)
class ExecutePhaseOutcome:
    status: Literal["done", "awaiting_human_review", "failed"]
    reason: str
    call_role: str | None = None
    phase_reached: str | None = None
    failure_kind: str | None = None
    retry: int = 1


@dataclass(frozen=True)
class _PhaseAttempt:
    retry: int
    phase_dir: Path
    last_message_path: Path | None
    prompt: str


@dataclass(frozen=True)
class _PhaseAgentRun:
    status: AgentStatus | None
    phase_reached: str
    failure: ExecutePhaseOutcome | None = None


@dataclass(frozen=True)
class _PhaseValidationResult:
    status: Literal["passed", "failed"]
    failure_kind: Literal["validation-failed", "validation-infra-failure"] | None = None
    summary: str | None = None
    focus: str | None = None
    returncode: int | None = None


def _phase_target_label(manifest: MigrationManifest, phase: PhaseSpec) -> str:
    return f"{manifest.name} {phase_file_reference(phase)} ({phase.name})"


def _phase_display_label(phase: PhaseSpec) -> str:
    return phase.name


def _require_phase_in_manifest(
    manifest: MigrationManifest, phase_name: str,
) -> None:
    for manifest_phase in manifest.phases:
        if manifest_phase.name == phase_name:
            return
    raise ContinuousRefactorError(f"Phase {phase_name!r} not found in manifest")


def _parse_ready_verdict(stdout: str) -> tuple[ReadyVerdict, str]:
    nonempty_lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not nonempty_lines:
        raise ContinuousRefactorError("Phase ready-check produced no output")

    for line in reversed(nonempty_lines):
        match = _READY_RE.match(line)
        if not match:
            continue
        verdict = match.group("verdict").lower()  # type: ignore[assignment]
        reason = match.group("reason").lstrip(" \u2014-").strip() or verdict
        return verdict, reason
    raise ContinuousRefactorError(
        f"Phase ready-check produced unrecognised output: {nonempty_lines[-1]!r}"
    )


def check_phase_ready(
    phase: PhaseSpec,
    manifest: MigrationManifest,
    repo_root: Path,
    artifacts: RunArtifacts,
    *,
    taste: str = "",
    attempt: int = 1,
    retry: int = 1,
    agent: str,
    model: str,
    effort: str,
    timeout: int | None,
    effort_metadata: dict[str, object] | None = None,
) -> tuple[ReadyVerdict, str]:
    prompt = compose_phase_ready_prompt(phase, manifest, taste)
    check_dir = artifacts.root / "phase-ready-check"
    check_dir.mkdir(parents=True, exist_ok=True)
    target_label = _phase_target_label(manifest, phase)
    display_label = _phase_display_label(phase)
    call_role = "phase.ready-check"

    artifacts.log_call_started(
        attempt=attempt,
        retry=retry,
        target=target_label,
        display_target=display_label,
        call_role=call_role,
        effort=effort_metadata,
    )

    try:
        result = maybe_run_agent(
            agent=agent,
            model=model,
            effort=effort,
            prompt=prompt,
            repo_root=repo_root,
            stdout_path=check_dir / "agent.stdout.log",
            stderr_path=check_dir / "agent.stderr.log",
            last_message_path=(
                check_dir / "agent-last-message.md" if agent == "codex" else None
            ),
            mirror_to_terminal=False,
            timeout=timeout,
        )
    except ContinuousRefactorError as error:
        artifacts.log_call_finished(
            attempt=attempt,
            retry=retry,
            target=target_label,
            display_target=display_label,
            call_role=call_role,
            status="failed",
            level="WARN",
            summary=str(error),
            effort=effort_metadata,
        )
        raise

    if result.returncode != 0:
        artifacts.log_call_finished(
            attempt=attempt,
            retry=retry,
            target=target_label,
            display_target=display_label,
            call_role=call_role,
            status="failed",
            level="WARN",
            returncode=result.returncode,
            summary=f"{agent} exited with code {result.returncode}",
            effort=effort_metadata,
        )
        process_error = subprocess.CalledProcessError(
            result.returncode,
            result.command,
            output=result.stdout,
            stderr=result.stderr,
        )
        raise ContinuousRefactorError(
            f"Phase ready-check agent failed with exit code {result.returncode}"
        ) from process_error

    artifacts.log_call_finished(
        attempt=attempt,
        retry=retry,
        target=target_label,
        display_target=display_label,
        call_role=call_role,
        status="finished",
        returncode=result.returncode,
        effort=effort_metadata,
    )
    return _parse_ready_verdict(result.stdout)


def _terminal_phase_failure(
    artifacts: RunArtifacts,
    *,
    attempt: int,
    retry: int,
    target_label: str,
    display_target_label: str,
    call_role: str,
    phase_reached: str | None,
    repo_root: Path,
    head_before: str,
    reason: str,
    failure_kind: str,
    returncode: int | None = None,
    summary: str | None = None,
    effort_metadata: dict[str, object] | None = None,
) -> ExecutePhaseOutcome:
    artifacts.log_call_finished(
        attempt=attempt,
        retry=retry,
        target=target_label,
        display_target=display_target_label,
        call_role=call_role,
        phase_reached=phase_reached,
        status="failed",
        level="WARN",
        returncode=returncode,
        summary=summary,
        effort=effort_metadata,
    )
    revert_to(repo_root, head_before)
    return ExecutePhaseOutcome(
        status="failed",
        reason=reason,
        call_role=call_role,
        phase_reached=phase_reached or call_role,
        failure_kind=failure_kind,
        retry=retry,
    )


def _phase_retry_context(
    target_label: str,
    call_role: str,
    summary: str,
    focus: str | None,
) -> str:
    lines = [
        f"- Previous attempt on `{target_label}` failed during `{call_role}`.",
        f"- Summary: {summary}",
    ]
    if focus:
        lines.append(f"- Next retry focus: {focus}")
    return "\n".join(lines)


def _prepare_phase_attempt(
    phase: PhaseSpec,
    manifest: MigrationManifest,
    taste: str,
    artifacts: RunArtifacts,
    *,
    attempt: int,
    retry: int,
    first_retry: int,
    agent: str,
    repo_root: Path,
    head_before: str,
    validation_command: str,
    retry_context: str | None,
) -> _PhaseAttempt:
    if retry > first_retry:
        revert_to(repo_root, head_before)

    phase_dir = artifacts.attempt_dir(attempt, retry=retry) / "phase-execute"
    phase_dir.mkdir(parents=True, exist_ok=True)
    last_message_path = (
        phase_dir / "agent-last-message.md" if agent == "codex" else None
    )
    prompt = compose_phase_execution_prompt(
        phase,
        manifest,
        taste,
        validation_command,
        retry_context=retry_context,
    )
    return _PhaseAttempt(
        retry=retry,
        phase_dir=phase_dir,
        last_message_path=last_message_path,
        prompt=prompt,
    )


def _run_phase_agent(
    phase_attempt: _PhaseAttempt,
    artifacts: RunArtifacts,
    *,
    attempt: int,
    target_label: str,
    display_target_label: str,
    repo_root: Path,
    head_before: str,
    agent: str,
    model: str,
    effort: str,
    effort_metadata: dict[str, object] | None,
    timeout: int | None,
) -> _PhaseAgentRun:
    artifacts.log_call_started(
        attempt=attempt,
        retry=phase_attempt.retry,
        target=target_label,
        display_target=display_target_label,
        call_role=_PHASE_EXECUTE_ROLE,
        effort=effort_metadata,
    )

    try:
        result = maybe_run_agent(
            agent=agent,
            model=model,
            effort=effort,
            prompt=phase_attempt.prompt,
            repo_root=repo_root,
            stdout_path=phase_attempt.phase_dir / "agent.stdout.log",
            stderr_path=phase_attempt.phase_dir / "agent.stderr.log",
            last_message_path=phase_attempt.last_message_path,
            mirror_to_terminal=False,
            timeout=timeout,
        )
    except ContinuousRefactorError as error:
        summary = sanitize_text(str(error), repo_root) or str(error)
        return _PhaseAgentRun(
            status=None,
            phase_reached=_PHASE_EXECUTE_ROLE,
            failure=_terminal_phase_failure(
                artifacts,
                attempt=attempt,
                retry=phase_attempt.retry,
                target_label=target_label,
                display_target_label=display_target_label,
                call_role=_PHASE_EXECUTE_ROLE,
                phase_reached=None,
                repo_root=repo_root,
                head_before=head_before,
                reason=summary,
                failure_kind=error_failure_kind(str(error)),
                summary=summary,
                effort_metadata=effort_metadata,
            ),
        )

    agent_status = read_status(
        agent,
        last_message_path=phase_attempt.last_message_path,
        fallback_text=result.stdout,
    )
    phase_reached = resolved_phase_reached(agent_status, _PHASE_EXECUTE_ROLE)

    if result.returncode != 0:
        summary, _ = status_summary(
            agent_status,
            fallback=f"{agent} exited with code {result.returncode}",
            repo_root=repo_root,
        )
        return _PhaseAgentRun(
            status=agent_status,
            phase_reached=phase_reached,
            failure=_terminal_phase_failure(
                artifacts,
                attempt=attempt,
                retry=phase_attempt.retry,
                target_label=target_label,
                display_target_label=display_target_label,
                call_role=_PHASE_EXECUTE_ROLE,
                phase_reached=phase_reached,
                repo_root=repo_root,
                head_before=head_before,
                reason=summary,
                failure_kind="agent-exited-nonzero",
                returncode=result.returncode,
                summary=summary,
                effort_metadata=effort_metadata,
            ),
        )

    artifacts.log_call_finished(
        attempt=attempt,
        retry=phase_attempt.retry,
        target=target_label,
        display_target=display_target_label,
        call_role=_PHASE_EXECUTE_ROLE,
        status="finished",
        returncode=result.returncode,
        effort=effort_metadata,
    )
    return _PhaseAgentRun(
        status=agent_status,
        phase_reached=phase_reached,
    )


def _run_phase_validation(
    phase_attempt: _PhaseAttempt,
    agent_run: _PhaseAgentRun,
    artifacts: RunArtifacts,
    *,
    attempt: int,
    target_label: str,
    display_target_label: str,
    repo_root: Path,
    validation_command: str,
) -> _PhaseValidationResult:
    artifacts.log_call_started(
        attempt=attempt,
        retry=phase_attempt.retry,
        target=target_label,
        display_target=display_target_label,
        call_role=_PHASE_VALIDATION_ROLE,
        phase_reached=agent_run.phase_reached,
    )
    try:
        test_result = run_tests(
            validation_command,
            repo_root,
            stdout_path=phase_attempt.phase_dir / "tests.stdout.log",
            stderr_path=phase_attempt.phase_dir / "tests.stderr.log",
            mirror_to_terminal=False,
        )
    except ContinuousRefactorError as error:
        summary, focus = status_summary(
            agent_run.status,
            fallback=sanitize_text(str(error), repo_root) or str(error),
            repo_root=repo_root,
        )
        return _PhaseValidationResult(
            status="failed",
            failure_kind="validation-infra-failure",
            summary=summary,
            focus=focus,
        )

    if test_result.returncode != 0:
        summary, focus = status_summary(
            agent_run.status,
            fallback=_VALIDATION_FAILED_SUMMARY,
            repo_root=repo_root,
        )
        return _PhaseValidationResult(
            status="failed",
            failure_kind="validation-failed",
            summary=summary,
            focus=focus,
            returncode=test_result.returncode,
        )

    artifacts.log_call_finished(
        attempt=attempt,
        retry=phase_attempt.retry,
        target=target_label,
        display_target=display_target_label,
        call_role=_PHASE_VALIDATION_ROLE,
        phase_reached=agent_run.phase_reached,
        status="finished",
        returncode=test_result.returncode,
    )
    return _PhaseValidationResult(status="passed")


def _can_retry_phase_validation(
    retry_number: int,
    max_attempts: int | None,
) -> bool:
    return max_attempts is None or retry_number < max_attempts


def _record_retryable_validation_failure(
    validation_result: _PhaseValidationResult,
    artifacts: RunArtifacts,
    *,
    attempt: int,
    retry: int,
    target_label: str,
    display_target_label: str,
    phase_reached: str,
    repo_root: Path,
    head_before: str,
) -> str:
    summary = validation_result.summary or _VALIDATION_FAILED_SUMMARY
    artifacts.log_call_finished(
        attempt=attempt,
        retry=retry,
        target=target_label,
        display_target=display_target_label,
        call_role=_PHASE_VALIDATION_ROLE,
        phase_reached=phase_reached,
        status="failed",
        level="WARN",
        returncode=validation_result.returncode,
        summary=summary,
    )
    revert_to(repo_root, head_before)
    return _phase_retry_context(
        target_label,
        _PHASE_VALIDATION_ROLE,
        summary,
        validation_result.focus,
    )


def _fail_phase_validation(
    validation_result: _PhaseValidationResult,
    artifacts: RunArtifacts,
    *,
    attempt: int,
    retry: int,
    target_label: str,
    display_target_label: str,
    phase_reached: str,
    repo_root: Path,
    head_before: str,
) -> ExecutePhaseOutcome:
    return _terminal_phase_failure(
        artifacts,
        attempt=attempt,
        retry=retry,
        target_label=target_label,
        display_target_label=display_target_label,
        call_role=_PHASE_VALIDATION_ROLE,
        phase_reached=phase_reached,
        repo_root=repo_root,
        head_before=head_before,
        reason=validation_result.summary or _VALIDATION_FAILED_SUMMARY,
        failure_kind=validation_result.failure_kind or "validation-failed",
        returncode=validation_result.returncode,
        summary=validation_result.summary,
    )


def _complete_phase(
    phase: PhaseSpec,
    manifest: MigrationManifest,
    live_dir: Path,
    *,
    status: AgentStatus | None,
    repo_root: Path,
    retry: int,
) -> ExecutePhaseOutcome:
    updated_manifest = complete_manifest_phase(
        manifest,
        phase.name,
        iso_timestamp(),
    )

    manifest_path = migration_root(live_dir, manifest.name) / "manifest.json"
    save_manifest(updated_manifest, manifest_path)

    reason = commit_rationale(
        status,
        fallback="Phase completed successfully",
        repo_root=repo_root,
    )
    return ExecutePhaseOutcome(
        status="done",
        reason=reason,
        retry=retry,
    )


def execute_phase(
    phase: PhaseSpec,
    manifest: MigrationManifest,
    taste: str,
    repo_root: Path,
    live_dir: Path,
    artifacts: RunArtifacts,
    *,
    attempt: int = 1,
    retry: int = 1,
    agent: str,
    model: str,
    effort: str,
    timeout: int | None,
    validation_command: str,
    max_attempts: int | None,
    effort_metadata: dict[str, object] | None = None,
) -> ExecutePhaseOutcome:
    _require_phase_in_manifest(manifest, phase.name)
    head_before = get_head_sha(repo_root)
    target_label = _phase_target_label(manifest, phase)
    display_target_label = _phase_display_label(phase)
    retry_context: str | None = None
    retry_number = retry

    while True:
        phase_attempt = _prepare_phase_attempt(
            phase,
            manifest,
            taste,
            artifacts,
            attempt=attempt,
            retry=retry_number,
            first_retry=retry,
            agent=agent,
            repo_root=repo_root,
            head_before=head_before,
            validation_command=validation_command,
            retry_context=retry_context,
        )
        agent_run = _run_phase_agent(
            phase_attempt,
            artifacts,
            attempt=attempt,
            target_label=target_label,
            display_target_label=display_target_label,
            repo_root=repo_root,
            head_before=head_before,
            agent=agent,
            model=model,
            effort=effort,
            effort_metadata=effort_metadata,
            timeout=timeout,
        )
        if agent_run.failure is not None:
            return agent_run.failure

        validation_result = _run_phase_validation(
            phase_attempt,
            agent_run,
            artifacts,
            attempt=attempt,
            target_label=target_label,
            display_target_label=display_target_label,
            repo_root=repo_root,
            validation_command=validation_command,
        )

        if validation_result.status == "passed":
            return _complete_phase(
                phase,
                manifest,
                live_dir,
                status=agent_run.status,
                repo_root=repo_root,
                retry=retry_number,
            )

        if not _can_retry_phase_validation(retry_number, max_attempts):
            return _fail_phase_validation(
                validation_result,
                artifacts,
                attempt=attempt,
                retry=retry_number,
                target_label=target_label,
                display_target_label=display_target_label,
                phase_reached=agent_run.phase_reached,
                repo_root=repo_root,
                head_before=head_before,
            )

        retry_context = _record_retryable_validation_failure(
            validation_result,
            artifacts,
            attempt=attempt,
            retry=retry_number,
            target_label=target_label,
            display_target_label=display_target_label,
            phase_reached=agent_run.phase_reached,
            repo_root=repo_root,
            head_before=head_before,
        )
        retry_number += 1
