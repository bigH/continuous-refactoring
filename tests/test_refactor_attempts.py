from __future__ import annotations

from pathlib import Path

import pytest

from continuous_refactoring import run_command
from continuous_refactoring.artifacts import (
    CommandCapture,
    ContinuousRefactorError,
    RunArtifacts,
    create_run_artifacts,
)
from continuous_refactoring.refactor_attempts import _run_refactor_attempt
from continuous_refactoring.targeting import Target

from conftest import init_repo


@pytest.fixture(autouse=True)
def _isolate_tmpdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "tmpdir").mkdir()
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmpdir"))


def _make_artifacts(repo_root: Path) -> RunArtifacts:
    return create_run_artifacts(
        repo_root=repo_root,
        agent="codex",
        model="fake",
        effort="low",
        test_command="uv run pytest",
    )


def _target() -> Target:
    return Target(
        description="src/demo.py",
        files=("src/demo.py",),
        provenance="paths",
    )


def _capture(path: Path, *, returncode: int = 0) -> CommandCapture:
    path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path = path.with_name("stderr.log")
    path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    return CommandCapture(
        command=("fake",),
        returncode=returncode,
        stdout="",
        stderr="",
        stdout_path=path,
        stderr_path=stderr_path,
    )


def test_run_refactor_attempt_agent_infra_failure_restores_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    artifacts = _make_artifacts(repo_root)
    head_before = run_command(["git", "rev-parse", "HEAD"], cwd=repo_root).stdout.strip()

    def fail_agent(**kwargs: object) -> CommandCapture:
        rr = Path(str(kwargs["repo_root"]))
        (rr / "bad_change.txt").write_text("bad\n", encoding="utf-8")
        raise ContinuousRefactorError("Command timed out after 1s: fake")

    monkeypatch.setattr(
        "continuous_refactoring.refactor_attempts.maybe_run_agent",
        fail_agent,
    )

    record = _run_refactor_attempt(
        repo_root=repo_root,
        artifacts=artifacts,
        target=_target(),
        attempt=1,
        retry=1,
        agent="codex",
        model="fake",
        effort="low",
        prompt="prompt",
        timeout=1,
        validation_command="uv run pytest",
        show_agent_logs=False,
        show_command_logs=False,
        commit_message_prefix="continuous refactor",
    )

    assert record.decision == "retry"
    assert record.retry_recommendation == "same-target"
    assert record.call_role == "refactor"
    assert record.failure_kind == "timeout"
    assert not (repo_root / "bad_change.txt").exists()
    head_after = run_command(["git", "rev-parse", "HEAD"], cwd=repo_root).stdout.strip()
    assert head_after == head_before


def test_run_refactor_attempt_validation_infra_failure_records_test_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    artifacts = _make_artifacts(repo_root)

    def ok_agent(**kwargs: object) -> CommandCapture:
        rr = Path(str(kwargs["repo_root"]))
        (rr / "bad_change.txt").write_text("bad\n", encoding="utf-8")
        stdout_path = Path(str(kwargs["stdout_path"]))
        return _capture(stdout_path)

    def fail_validation(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        raise ContinuousRefactorError("pytest executable missing")

    monkeypatch.setattr(
        "continuous_refactoring.refactor_attempts.maybe_run_agent",
        ok_agent,
    )
    monkeypatch.setattr(
        "continuous_refactoring.refactor_attempts.run_tests",
        fail_validation,
    )

    record = _run_refactor_attempt(
        repo_root=repo_root,
        artifacts=artifacts,
        target=_target(),
        attempt=1,
        retry=1,
        agent="codex",
        model="fake",
        effort="low",
        prompt="prompt",
        timeout=None,
        validation_command="uv run pytest",
        show_agent_logs=False,
        show_command_logs=False,
        commit_message_prefix="continuous refactor",
    )

    assert record.decision == "retry"
    assert record.call_role == "validation"
    assert record.failure_kind == "validation-infra-failure"
    assert (
        record.tests_stdout_path
        == artifacts.attempt_dir(1) / "refactor" / "tests.stdout.log"
    )
    assert (
        record.tests_stderr_path
        == artifacts.attempt_dir(1) / "refactor" / "tests.stderr.log"
    )
    assert not (repo_root / "bad_change.txt").exists()
