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
    "PhaseAttemptResult",
    "RunArtifacts",
    "create_run_artifacts",
    "default_artifacts_root",
    "iso_timestamp",
]


class ContinuousRefactorError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandCapture:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    stdout_path: Path
    stderr_path: Path


@dataclass(frozen=True)
class PhaseAttemptResult:
    passed: bool
    failure_context: str
    target: str | None
    agent_returncode: int
    test_returncode: int | None


@dataclass
class AttemptStats:
    attempt: int
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
    metadata_path: Path
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

    def attempt_dir(self, attempt: int) -> Path:
        path = self.root / f"attempt-{attempt:03d}"
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

    def record_phase(
        self,
        *,
        attempt: int,
        phase: str,
        outcome: str,
        target: str | None,
        agent_returncode: int,
        test_returncode: int | None,
        change_count: int | None,
    ) -> None:
        stats = self.ensure_attempt(attempt)
        if phase == "refactor":
            stats.refactor_target = target
            stats.refactor_outcome = outcome
            stats.refactor_agent_returncode = agent_returncode
            stats.refactor_test_returncode = test_returncode
            stats.refactor_change_count = change_count
        else:
            stats.fix_target = target
            stats.fix_outcome = outcome
            stats.fix_agent_returncode = agent_returncode
            stats.fix_test_returncode = test_returncode
            stats.fix_change_count = change_count
        self.counts[f"{phase}_{outcome}"] += 1
        self.write_summary()

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

    def record_baseline_failure(self) -> None:
        self.counts["baseline_failures"] += 1
        self.write_summary()

    def finish(self, status: str, error_message: str | None = None) -> None:
        self.finished_at = iso_timestamp()
        self.final_status = status
        self.error_message = error_message
        self.write_summary()

    def write_metadata(self) -> None:
        metadata = {
            "run_id": self.run_id,
            "artifact_root": str(self.root),
            "repo_root": str(self.repo_root),
            "agent": self.agent,
            "model": self.model,
            "effort": self.effort,
            "test_command": self.test_command,
            "started_at": self.started_at,
        }
        self.metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

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
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def default_artifacts_root() -> Path:
    tmpdir = os.environ.get("TMPDIR")
    if tmpdir:
        return Path(tmpdir)
    return Path(tempfile.gettempdir())


def create_run_artifacts(
    repo_root: Path,
    *,
    agent: str,
    model: str,
    effort: str,
    test_command: str,
) -> RunArtifacts:
    started_at = iso_timestamp()
    run_id = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S-%f")
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
        metadata_path=root / "metadata.json",
        started_at=started_at,
    )
    artifacts.write_metadata()
    artifacts.write_summary()
    return artifacts
