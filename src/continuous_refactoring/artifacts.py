from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


__all__ = [
    "AttemptStats",
    "CommandCapture",
    "ContinuousRefactorError",
    "RunArtifacts",
    "create_run_artifacts",
    "default_artifacts_root",
    "iso_timestamp",
]


class ContinuousRefactorError(RuntimeError):
    pass


_UNSET = object()


@dataclass(frozen=True)
class CommandCapture:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    stdout_path: Path
    stderr_path: Path


@dataclass
class AttemptStats:
    attempt: int
    target: str | None = None
    retry: int | None = None
    call_role: str | None = None
    phase_reached: str | None = None
    decision: str | None = None
    retry_recommendation: str | None = None
    failure_kind: str | None = None
    failure_summary: str | None = None
    reason_doc_path: str | None = None
    refactor_target: str | None = None
    refactor_outcome: str | None = None
    refactor_agent_returncode: int | None = None
    refactor_test_returncode: int | None = None
    refactor_change_count: int | None = None
    fix_target: str | None = None
    fix_outcome: str | None = None
    fix_agent_returncode: int | None = None
    fix_test_returncode: int | None = None
    fix_change_count: int | None = None
    commit_sha: str | None = None
    commit_phase: str | None = None
    pushed: bool = False


@dataclass
class RunArtifacts:
    root: Path
    run_id: str
    repo_root: Path
    agent: str
    model: str
    effort: str
    test_command: str
    events_path: Path
    summary_path: Path
    log_path: Path
    started_at: str
    finished_at: str | None = None
    final_status: str = "running"
    error_message: str | None = None
    attempts: dict[int, AttemptStats] = field(default_factory=dict)
    counts: dict[str, int] = field(
        default_factory=lambda: {
            "attempts_started": 0,
            "baseline_failures": 0,
            "refactor_agent_failed": 0,
            "refactor_failed_tests": 0,
            "refactor_passed_with_changes": 0,
            "refactor_passed_no_changes": 0,
            "fix_agent_failed": 0,
            "fix_failed_tests": 0,
            "fix_passed_with_changes": 0,
            "fix_passed_no_changes": 0,
            "commits_created": 0,
            "pushes_completed": 0,
        }
    )

    def attempt_dir(self, attempt: int, retry: int = 1) -> Path:
        if attempt < 1:
            raise ValueError(f"attempt must be >= 1, got {attempt}")
        if retry < 1:
            raise ValueError(f"retry must be >= 1, got {retry}")
        base = self.root / f"attempt-{attempt:03d}"
        path = base if retry == 1 else base / f"retry-{retry:02d}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def baseline_dir(self, label: str) -> Path:
        path = self.root / "baseline" / label
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ensure_attempt(self, attempt: int) -> AttemptStats:
        if attempt not in self.attempts:
            self.attempts[attempt] = AttemptStats(attempt=attempt)
        return self.attempts[attempt]

    def update_attempt(
        self,
        attempt: int,
        *,
        target: str | None | object = _UNSET,
        retry: int | None | object = _UNSET,
        call_role: str | None | object = _UNSET,
        phase_reached: str | None | object = _UNSET,
        decision: str | None | object = _UNSET,
        retry_recommendation: str | None | object = _UNSET,
        failure_kind: str | None | object = _UNSET,
        failure_summary: str | None | object = _UNSET,
        reason_doc_path: Path | None | object = _UNSET,
    ) -> None:
        stats = self.ensure_attempt(attempt)
        if target is not _UNSET:
            stats.target = target
        if retry is not _UNSET:
            stats.retry = retry
        if call_role is not _UNSET:
            stats.call_role = call_role
        if phase_reached is not _UNSET:
            stats.phase_reached = phase_reached
        if decision is not _UNSET:
            stats.decision = decision
        if retry_recommendation is not _UNSET:
            stats.retry_recommendation = retry_recommendation
        if failure_kind is not _UNSET:
            stats.failure_kind = failure_kind
        if failure_summary is not _UNSET:
            stats.failure_summary = failure_summary
        if reason_doc_path is not _UNSET:
            stats.reason_doc_path = (
                str(reason_doc_path) if reason_doc_path is not None else None
            )
        self.write_summary()

    def log(self, level: str, message: str, **fields: object) -> None:
        timestamp = iso_timestamp()
        line = f"[{level}] {message}"
        print(line)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {line}\n")
        event = {"timestamp": timestamp, "level": level, "message": message, **fields}
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        self.write_summary()

    def mark_attempt_started(self, attempt: int) -> None:
        self.counts["attempts_started"] += 1
        self.ensure_attempt(attempt)
        self.write_summary()

    def log_call_started(
        self,
        *,
        attempt: int,
        retry: int,
        target: str,
        call_role: str,
        phase_reached: str | None = None,
    ) -> None:
        self.update_attempt(
            attempt,
            target=target,
            retry=retry,
            call_role=call_role,
            phase_reached=phase_reached or call_role,
        )
        self.log(
            "INFO",
            f"call start: {call_role} — {target}",
            event="call_started",
            attempt=attempt,
            retry=retry,
            target=target,
            call_role=call_role,
            phase_reached=phase_reached or call_role,
        )

    def log_call_finished(
        self,
        *,
        attempt: int,
        retry: int,
        target: str,
        call_role: str,
        phase_reached: str | None = None,
        status: str,
        level: str = "INFO",
        returncode: int | None = None,
        summary: str | None = None,
    ) -> None:
        self.update_attempt(
            attempt,
            target=target,
            retry=retry,
            call_role=call_role,
            phase_reached=phase_reached or call_role,
            failure_summary=summary,
        )
        self.log(
            level,
            f"call {status}: {call_role} — {target}",
            event="call_finished",
            attempt=attempt,
            retry=retry,
            target=target,
            call_role=call_role,
            phase_reached=phase_reached or call_role,
            call_status=status,
            returncode=returncode,
            summary=summary,
        )

    def log_transition(
        self,
        *,
        attempt: int,
        retry: int,
        target: str,
        call_role: str,
        phase_reached: str,
        decision: str,
        retry_recommendation: str,
        failure_kind: str,
        summary: str,
        reason_doc_path: Path | None,
    ) -> None:
        self.update_attempt(
            attempt,
            target=target,
            retry=retry,
            call_role=call_role,
            phase_reached=phase_reached,
            decision=decision,
            retry_recommendation=retry_recommendation,
            failure_kind=failure_kind,
            failure_summary=summary,
            reason_doc_path=reason_doc_path,
        )
        self.log(
            "WARN",
            f"target transition: {decision}/{retry_recommendation} — {target}",
            event="target_transition",
            attempt=attempt,
            retry=retry,
            target=target,
            call_role=call_role,
            phase_reached=phase_reached,
            decision=decision,
            retry_recommendation=retry_recommendation,
            failure_kind=failure_kind,
            summary=summary,
            reason_doc_path=str(reason_doc_path) if reason_doc_path else None,
        )

    def record_commit(self, attempt: int, phase: str, commit_sha: str) -> None:
        stats = self.ensure_attempt(attempt)
        stats.commit_sha = commit_sha
        stats.commit_phase = phase
        self.counts["commits_created"] += 1
        self.write_summary()

    def record_push(self, attempt: int) -> None:
        stats = self.ensure_attempt(attempt)
        stats.pushed = True
        self.counts["pushes_completed"] += 1
        self.write_summary()

    def finish(self, status: str, error_message: str | None = None) -> None:
        self.finished_at = iso_timestamp()
        self.final_status = status
        self.error_message = error_message
        self.write_summary()

    def write_summary(self) -> None:
        summary = {
            "run_id": self.run_id,
            "artifact_root": str(self.root),
            "repo_root": str(self.repo_root),
            "agent": self.agent,
            "model": self.model,
            "effort": self.effort,
            "test_command": self.test_command,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "final_status": self.final_status,
            "error_message": self.error_message,
            "counts": self.counts,
            "attempts": [asdict(self.attempts[key]) for key in sorted(self.attempts)],
        }
        self.summary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def iso_timestamp() -> str:
    return _now().isoformat(timespec="milliseconds")


def _now() -> datetime:
    return datetime.now().astimezone()


def default_artifacts_root() -> Path:
    return Path(os.environ.get("TMPDIR") or tempfile.gettempdir())


def create_run_artifacts(
    repo_root: Path,
    *,
    agent: str,
    model: str,
    effort: str,
    test_command: str,
) -> RunArtifacts:
    started_at_dt = _now()
    started_at = started_at_dt.isoformat(timespec="milliseconds")
    run_id = started_at_dt.strftime("%Y%m%dT%H%M%S-%f")
    root = default_artifacts_root() / "continuous-refactoring" / run_id
    root.mkdir(parents=True, exist_ok=False)
    artifacts = RunArtifacts(
        root=root,
        run_id=run_id,
        repo_root=repo_root,
        agent=agent,
        model=model,
        effort=effort,
        test_command=test_command,
        events_path=root / "events.jsonl",
        summary_path=root / "summary.json",
        log_path=root / "run.log",
        started_at=started_at,
    )
    artifacts.write_summary()
    return artifacts
