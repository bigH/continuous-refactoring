from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from continuous_refactoring.artifacts import RunArtifacts
    from continuous_refactoring.migrations import MigrationManifest, PhaseSpec

__all__ = [
    "ExecutePhaseOutcome",
    "ReadyVerdict",
    "check_phase_ready",
    "execute_phase",
]

from continuous_refactoring.agent import maybe_run_agent, run_tests
from continuous_refactoring.artifacts import ContinuousRefactorError, iso_timestamp
from continuous_refactoring.decisions import (
    error_failure_kind,
    read_status,
    resolved_phase_reached,
    sanitize_text,
    status_summary,
)
from continuous_refactoring.git import get_head_sha, revert_to
from continuous_refactoring.migrations import (
    advance_phase_cursor,
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


@dataclass(frozen=True)
class ExecutePhaseOutcome:
    status: Literal["done", "awaiting_human_review", "failed"]
    reason: str
    call_role: str | None = None
    phase_reached: str | None = None
    failure_kind: str | None = None
    retry: int = 1


def _phase_target_label(manifest: MigrationManifest, phase: PhaseSpec) -> str:
    return f"{manifest.name} {phase_file_reference(phase)} ({phase.name})"


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
    attempt: int = 1,
    retry: int = 1,
    agent: str,
    model: str,
    effort: str,
    timeout: int | None,
) -> tuple[ReadyVerdict, str]:
    prompt = compose_phase_ready_prompt(phase, manifest)
    check_dir = artifacts.root / "phase-ready-check"
    check_dir.mkdir(parents=True, exist_ok=True)
    target_label = _phase_target_label(manifest, phase)
    call_role = "phase.ready-check"

    artifacts.log_call_started(
        attempt=attempt,
        retry=retry,
        target=target_label,
        call_role=call_role,
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
            call_role=call_role,
            status="failed",
            level="WARN",
            summary=str(error),
        )
        raise

    if result.returncode != 0:
        artifacts.log_call_finished(
            attempt=attempt,
            retry=retry,
            target=target_label,
            call_role=call_role,
            status="failed",
            level="WARN",
            returncode=result.returncode,
            summary=f"{agent} exited with code {result.returncode}",
        )
        raise ContinuousRefactorError(
            f"Phase ready-check agent failed with exit code {result.returncode}"
        )

    artifacts.log_call_finished(
        attempt=attempt,
        retry=retry,
        target=target_label,
        call_role=call_role,
        status="finished",
        returncode=result.returncode,
    )
    return _parse_ready_verdict(result.stdout)


def _fail_execute(
    artifacts: RunArtifacts,
    *,
    attempt: int,
    retry: int,
    target_label: str,
    call_role: str,
    phase_reached: str | None,
    repo_root: Path,
    head_before: str,
    reason: str,
    failure_kind: str,
    returncode: int | None = None,
    summary: str | None = None,
) -> ExecutePhaseOutcome:
    artifacts.log_call_finished(
        attempt=attempt,
        retry=retry,
        target=target_label,
        call_role=call_role,
        phase_reached=phase_reached,
        status="failed",
        level="WARN",
        returncode=returncode,
        summary=summary,
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
) -> ExecutePhaseOutcome:
    head_before = get_head_sha(repo_root)
    target_label = _phase_target_label(manifest, phase)
    execute_role = "phase.execute"
    validation_role = "phase.validation"
    retry_context: str | None = None
    current_retry = retry - 1

    while True:
        current_retry += 1
        if current_retry > retry:
            revert_to(repo_root, head_before)

        phase_dir = artifacts.attempt_dir(attempt, retry=current_retry) / "phase-execute"
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

        artifacts.log_call_started(
            attempt=attempt,
            retry=current_retry,
            target=target_label,
            call_role=execute_role,
        )

        try:
            result = maybe_run_agent(
                agent=agent,
                model=model,
                effort=effort,
                prompt=prompt,
                repo_root=repo_root,
                stdout_path=phase_dir / "agent.stdout.log",
                stderr_path=phase_dir / "agent.stderr.log",
                last_message_path=last_message_path,
                mirror_to_terminal=False,
                timeout=timeout,
            )
        except ContinuousRefactorError as error:
            return _fail_execute(
                artifacts,
                attempt=attempt,
                retry=current_retry,
                target_label=target_label,
                call_role=execute_role,
                phase_reached=None,
                repo_root=repo_root,
                head_before=head_before,
                reason=sanitize_text(str(error), repo_root) or str(error),
                failure_kind=error_failure_kind(str(error)),
                summary=sanitize_text(str(error), repo_root) or str(error),
            )

        agent_status = read_status(
            agent,
            last_message_path=last_message_path,
            fallback_text=result.stdout,
        )
        execute_phase_reached = resolved_phase_reached(agent_status, execute_role)

        if result.returncode != 0:
            reason = f"{agent} exited with code {result.returncode}"
            summary, _focus = status_summary(
                agent_status,
                fallback=reason,
                repo_root=repo_root,
            )
            return _fail_execute(
                artifacts,
                attempt=attempt,
                retry=current_retry,
                target_label=target_label,
                call_role=execute_role,
                phase_reached=execute_phase_reached,
                repo_root=repo_root,
                head_before=head_before,
                reason=summary,
                failure_kind="agent-exited-nonzero",
                returncode=result.returncode,
                summary=summary,
            )

        artifacts.log_call_finished(
            attempt=attempt,
            retry=current_retry,
            target=target_label,
            call_role=execute_role,
            status="finished",
            returncode=result.returncode,
        )
        artifacts.log_call_started(
            attempt=attempt,
            retry=current_retry,
            target=target_label,
            call_role=validation_role,
            phase_reached=execute_phase_reached,
        )
        try:
            test_result = run_tests(
                validation_command,
                repo_root,
                stdout_path=phase_dir / "tests.stdout.log",
                stderr_path=phase_dir / "tests.stderr.log",
                mirror_to_terminal=False,
            )
        except ContinuousRefactorError as error:
            summary, focus = status_summary(
                agent_status,
                fallback=sanitize_text(str(error), repo_root) or str(error),
                repo_root=repo_root,
            )
            if max_attempts is None or current_retry < max_attempts:
                artifacts.log_call_finished(
                    attempt=attempt,
                    retry=current_retry,
                    target=target_label,
                    call_role=validation_role,
                    phase_reached=execute_phase_reached,
                    status="failed",
                    level="WARN",
                    summary=summary,
                )
                revert_to(repo_root, head_before)
                retry_context = _phase_retry_context(
                    target_label,
                    validation_role,
                    summary,
                    focus,
                )
                continue
            return _fail_execute(
                artifacts,
                attempt=attempt,
                retry=current_retry,
                target_label=target_label,
                call_role=validation_role,
                phase_reached=execute_phase_reached,
                repo_root=repo_root,
                head_before=head_before,
                reason=summary,
                failure_kind="validation-infra-failure",
                summary=summary,
            )

        if test_result.returncode != 0:
            summary, focus = status_summary(
                agent_status,
                fallback="validation failed after phase execution",
                repo_root=repo_root,
            )
            if max_attempts is None or current_retry < max_attempts:
                artifacts.log_call_finished(
                    attempt=attempt,
                    retry=current_retry,
                    target=target_label,
                    call_role=validation_role,
                    phase_reached=execute_phase_reached,
                    status="failed",
                    level="WARN",
                    returncode=test_result.returncode,
                    summary=summary,
                )
                revert_to(repo_root, head_before)
                retry_context = _phase_retry_context(
                    target_label,
                    validation_role,
                    summary,
                    focus,
                )
                continue
            return _fail_execute(
                artifacts,
                attempt=attempt,
                retry=current_retry,
                target_label=target_label,
                call_role=validation_role,
                phase_reached=execute_phase_reached,
                repo_root=repo_root,
                head_before=head_before,
                reason=summary,
                failure_kind="validation-failed",
                returncode=test_result.returncode,
                summary=summary,
            )

        artifacts.log_call_finished(
            attempt=attempt,
            retry=current_retry,
            target=target_label,
            call_role=validation_role,
            phase_reached=execute_phase_reached,
            status="finished",
            returncode=test_result.returncode,
        )

        phase_index = None
        for index, manifest_phase in enumerate(manifest.phases):
            if manifest_phase.name == phase.name:
                phase_index = index
                break
        if phase_index is None:
            raise ContinuousRefactorError(f"Phase {phase.name!r} not found in manifest")
        updated_phases = tuple(
            replace(p, done=True) if i == phase_index else p
            for i, p in enumerate(manifest.phases)
        )
        now = iso_timestamp()
        updated_manifest = replace(
            manifest,
            phases=updated_phases,
            last_touch=now,
            wake_up_on=None,
            awaiting_human_review=False,
            human_review_reason=None,
            cooldown_until=None,
        )
        next_phase_name = advance_phase_cursor(manifest, phase.name)
        if next_phase_name is None:
            updated_manifest = replace(
                updated_manifest,
                current_phase="",
                status="done",
            )
        else:
            updated_manifest = replace(updated_manifest, current_phase=next_phase_name)

        manifest_path = migration_root(live_dir, manifest.name) / "manifest.json"
        save_manifest(updated_manifest, manifest_path)

        return ExecutePhaseOutcome(
            status="done",
            reason="Phase completed successfully",
            retry=current_retry,
        )
