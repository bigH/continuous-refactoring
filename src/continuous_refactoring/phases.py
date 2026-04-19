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

from continuous_refactoring.agent import maybe_run_agent, run_tests, summarize_output
from continuous_refactoring.artifacts import ContinuousRefactorError, iso_timestamp
from continuous_refactoring.git import get_head_sha, revert_to
from continuous_refactoring.migrations import migration_root, save_manifest
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
    target_label = (
        f"{manifest.name} phase-{manifest.current_phase}/{phase.name}"
    )
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


def _find_phase_index(manifest: MigrationManifest, phase: PhaseSpec) -> int:
    for i, p in enumerate(manifest.phases):
        if p.name == phase.name and p.file == phase.file:
            return i
    raise ContinuousRefactorError(f"Phase {phase.name!r} not found in manifest")


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
) -> ExecutePhaseOutcome:
    prompt = compose_phase_execution_prompt(phase, manifest, taste)
    phase_dir = artifacts.root / "phase-execute"
    phase_dir.mkdir(parents=True, exist_ok=True)

    head_before = get_head_sha(repo_root)
    target_label = (
        f"{manifest.name} phase-{manifest.current_phase}/{phase.name}"
    )
    execute_role = "phase.execute"
    validation_role = "phase.validation"

    artifacts.log_call_started(
        attempt=attempt,
        retry=retry,
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
            last_message_path=(
                phase_dir / "agent-last-message.md" if agent == "codex" else None
            ),
            mirror_to_terminal=False,
            timeout=timeout,
        )
    except ContinuousRefactorError as error:
        return _fail_execute(
            artifacts,
            attempt=attempt, retry=retry, target_label=target_label,
            call_role=execute_role, phase_reached=None,
            repo_root=repo_root, head_before=head_before,
            reason=str(error), failure_kind="agent-infra-failure",
            summary=str(error),
        )

    if result.returncode != 0:
        reason = f"{agent} exited with code {result.returncode}"
        return _fail_execute(
            artifacts,
            attempt=attempt, retry=retry, target_label=target_label,
            call_role=execute_role, phase_reached=None,
            repo_root=repo_root, head_before=head_before,
            reason=reason, failure_kind="agent-exited-nonzero",
            returncode=result.returncode, summary=reason,
        )

    artifacts.log_call_finished(
        attempt=attempt,
        retry=retry,
        target=target_label,
        call_role=execute_role,
        status="finished",
        returncode=result.returncode,
    )
    artifacts.log_call_started(
        attempt=attempt,
        retry=retry,
        target=target_label,
        call_role=validation_role,
        phase_reached=execute_role,
    )
    try:
        test_result = run_tests(
            artifacts.test_command,
            repo_root,
            stdout_path=phase_dir / "tests.stdout.log",
            stderr_path=phase_dir / "tests.stderr.log",
            mirror_to_terminal=False,
        )
    except ContinuousRefactorError as error:
        return _fail_execute(
            artifacts,
            attempt=attempt, retry=retry, target_label=target_label,
            call_role=validation_role, phase_reached=execute_role,
            repo_root=repo_root, head_before=head_before,
            reason=str(error), failure_kind="validation-infra-failure",
            summary=str(error),
        )

    if test_result.returncode != 0:
        return _fail_execute(
            artifacts,
            attempt=attempt, retry=retry, target_label=target_label,
            call_role=validation_role, phase_reached=execute_role,
            repo_root=repo_root, head_before=head_before,
            reason=f"Tests failed: {summarize_output(test_result)}",
            failure_kind="validation-failed",
            returncode=test_result.returncode,
            summary="validation failed after phase execution",
        )

    artifacts.log_call_finished(
        attempt=attempt,
        retry=retry,
        target=target_label,
        call_role=validation_role,
        phase_reached=execute_role,
        status="finished",
        returncode=test_result.returncode,
    )

    phase_index = _find_phase_index(manifest, phase)
    updated_phases = tuple(
        replace(p, done=True) if i == phase_index else p
        for i, p in enumerate(manifest.phases)
    )
    now = iso_timestamp()
    updated_manifest = replace(manifest, phases=updated_phases, last_touch=now)
    if phase_index == manifest.current_phase:
        updated_manifest = replace(
            updated_manifest, current_phase=manifest.current_phase + 1,
        )

    manifest_path = migration_root(live_dir, manifest.name) / "manifest.json"
    save_manifest(updated_manifest, manifest_path)

    return ExecutePhaseOutcome(status="done", reason="Phase completed successfully")
