from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

__all__ = [
    "_finalize_commit",
    "_PreservedFile",
    "_PreservedWorkspaceTree",
    "_preserve_workspace_tree",
    "_reset_to_source_baseline",
    "_retry_context",
    "_run_refactor_attempt",
]

if TYPE_CHECKING:
    from continuous_refactoring.artifacts import RunArtifacts

from continuous_refactoring.agent import maybe_run_agent, run_tests
from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.commit_messages import (
    build_commit_message,
    commit_rationale,
)
from continuous_refactoring.decisions import (
    DecisionRecord,
    default_retry_recommendation,
    error_failure_kind,
    read_status,
    resolved_phase_reached,
    sanitize_text,
    status_summary,
)
from continuous_refactoring.git import (
    discard_workspace_changes,
    get_head_sha,
    git_commit,
    repo_change_count,
    revert_to,
    run_command,
)
from continuous_refactoring.targeting import Target


@dataclass(frozen=True)
class _PreservedFile:
    relative_path: Path
    content: bytes


@dataclass(frozen=True)
class _PreservedWorkspaceTree:
    files: tuple[_PreservedFile, ...]

    def restore(self, repo_root: Path) -> None:
        for preserved in self.files:
            path = repo_root / preserved.relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(preserved.content)


def _preserve_workspace_tree(
    repo_root: Path,
    root: Path | None,
) -> _PreservedWorkspaceTree | None:
    if root is None:
        return None
    try:
        root.relative_to(repo_root)
    except ValueError:
        return None
    if not root.exists():
        return None

    files = tuple(
        _PreservedFile(path.relative_to(repo_root), path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )
    if not files:
        return None
    return _PreservedWorkspaceTree(files)


def _reset_to_source_baseline(
    repo_root: Path,
    revision: str,
    preserved_workspace: _PreservedWorkspaceTree | None,
) -> None:
    revert_to(repo_root, revision)
    if preserved_workspace is not None:
        preserved_workspace.restore(repo_root)


def _retry_context(record: DecisionRecord) -> str:
    lines = [
        f"- Previous attempt on `{record.target}` failed during `{record.call_role}`.",
        f"- Summary: {record.summary}",
    ]
    if record.next_retry_focus:
        lines.append(f"- Next retry focus: {record.next_retry_focus}")
    return "\n".join(lines)


def _decision_record(
    *,
    decision: str,
    retry_recommendation: str,
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


def _restore_and_retry(
    *,
    repo_root: Path,
    head_before: str,
    preserved_workspace: _PreservedWorkspaceTree | None,
    target: str,
    call_role: str,
    phase_reached: str,
    failure_kind: str,
    summary: str,
    next_retry_focus: str | None,
    agent_last_message_path: Path | None,
    agent_stdout_path: Path | None,
    agent_stderr_path: Path | None,
    tests_stdout_path: Path | None = None,
    tests_stderr_path: Path | None = None,
) -> DecisionRecord:
    _reset_to_source_baseline(repo_root, head_before, preserved_workspace)
    return _decision_record(
        decision="retry",
        retry_recommendation="same-target",
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

    if head_after != head_before:
        run_command(["git", "reset", "--soft", head_before], cwd=repo_root)

    commit = git_commit(repo_root, commit_message)
    artifacts.record_commit(attempt, phase, commit)
    print(f"Committed: {commit}")
    return commit


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
    preserved_workspace: _PreservedWorkspaceTree | None = None,
    effort_metadata: dict[str, object] | None = None,
) -> DecisionRecord:
    discard_workspace_changes(repo_root)
    if preserved_workspace is not None:
        preserved_workspace.restore(repo_root)
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
        effort=effort_metadata,
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
            effort=effort_metadata,
        )
        agent_status = read_status(
            agent,
            last_message_path=last_message_path,
            fallback_text=None,
        )
        summary, focus = status_summary(
            agent_status,
            fallback=sanitize_text(str(error), repo_root) or str(error),
            repo_root=repo_root,
        )
        return _restore_and_retry(
            repo_root=repo_root,
            head_before=head_before,
            preserved_workspace=preserved_workspace,
            target=target.description,
            call_role=call_role,
            phase_reached=resolved_phase_reached(agent_status, phase_reached),
            failure_kind=error_failure_kind(str(error)),
            summary=summary,
            next_retry_focus=focus,
            agent_last_message_path=last_message_path,
            agent_stdout_path=agent_stdout,
            agent_stderr_path=agent_stderr,
        )

    agent_status = read_status(
        agent,
        last_message_path=last_message_path,
        fallback_text=agent_result.stdout,
    )
    if agent_result.returncode != 0:
        summary, focus = status_summary(
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
            effort=effort_metadata,
        )
        return _restore_and_retry(
            repo_root=repo_root,
            head_before=head_before,
            preserved_workspace=preserved_workspace,
            target=target.description,
            call_role=call_role,
            phase_reached=resolved_phase_reached(agent_status, phase_reached),
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
        effort=effort_metadata,
    )

    validation_role = "validation"
    artifacts.log_call_started(
        attempt=attempt,
        retry=retry,
        target=target.description,
        call_role=validation_role,
        phase_reached=resolved_phase_reached(agent_status, phase_reached),
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
            phase_reached=resolved_phase_reached(agent_status, phase_reached),
            status="failed",
            level="WARN",
            summary=str(error),
        )
        summary, focus = status_summary(
            agent_status,
            fallback=sanitize_text(str(error), repo_root) or str(error),
            repo_root=repo_root,
        )
        return _restore_and_retry(
            repo_root=repo_root,
            head_before=head_before,
            preserved_workspace=preserved_workspace,
            target=target.description,
            call_role=validation_role,
            phase_reached=resolved_phase_reached(agent_status, phase_reached),
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
        summary, focus = status_summary(
            agent_status,
            fallback="validation failed after refactor",
            repo_root=repo_root,
        )
        artifacts.log_call_finished(
            attempt=attempt,
            retry=retry,
            target=target.description,
            call_role=validation_role,
            phase_reached=resolved_phase_reached(agent_status, phase_reached),
            status="failed",
            level="WARN",
            returncode=validation_result.returncode,
            summary=summary,
        )
        return _restore_and_retry(
            repo_root=repo_root,
            head_before=head_before,
            preserved_workspace=preserved_workspace,
            target=target.description,
            call_role=validation_role,
            phase_reached=resolved_phase_reached(agent_status, phase_reached),
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
        phase_reached=resolved_phase_reached(agent_status, phase_reached),
        status="finished",
        returncode=validation_result.returncode,
    )

    if agent_status and agent_status.decision in {"retry", "abandon", "blocked"}:
        _reset_to_source_baseline(repo_root, head_before, preserved_workspace)
        summary, focus = status_summary(
            agent_status,
            fallback=f"agent requested {agent_status.decision}",
            repo_root=repo_root,
        )
        decision = agent_status.decision
        retry_recommendation = (
            agent_status.retry_recommendation
            or default_retry_recommendation(decision)
        )
        return _decision_record(
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

    rationale = commit_rationale(
        agent_status,
        fallback=(
            sanitize_text(agent_result.stdout, repo_root)
            or f"Validated cleanup for {target.description}."
        ),
        repo_root=repo_root,
    )
    _finalize_commit(
        repo_root,
        head_before,
        build_commit_message(
            f"{commit_message_prefix}: {target.description}",
            why=rationale,
            validation=validation_command,
        ),
        artifacts=artifacts,
        attempt=attempt,
        phase="refactor",
    )

    return _decision_record(
        decision="commit",
        retry_recommendation="none",
        target=target.description,
        call_role=validation_role,
        phase_reached=resolved_phase_reached(agent_status, phase_reached),
        failure_kind="none",
        summary=rationale,
        agent_last_message_path=last_message_path,
        agent_stdout_path=agent_result.stdout_path,
        agent_stderr_path=agent_result.stderr_path,
        tests_stdout_path=validation_result.stdout_path,
        tests_stderr_path=validation_result.stderr_path,
    )
