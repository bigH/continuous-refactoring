from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import continuous_refactoring

from conftest import init_repo


def test_discard_workspace_changes_restores_tracked_files_and_removes_untracked(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    starting_branch = continuous_refactoring.current_branch(repo)

    readme = repo / "README.md"
    readme.write_text("changed\n", encoding="utf-8")
    (repo / "scratch.txt").write_text("scratch\n", encoding="utf-8")

    continuous_refactoring.discard_workspace_changes(repo)

    assert readme.read_text(encoding="utf-8") == "seed\n"
    assert not (repo / "scratch.txt").exists()
    assert continuous_refactoring.current_branch(repo) == starting_branch
    assert continuous_refactoring.workspace_status_lines(repo) == []


def test_revert_to_restores_requested_head_and_removes_untracked(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    starting_branch = continuous_refactoring.current_branch(repo)
    original_head = continuous_refactoring.get_head_sha(repo)

    readme = repo / "README.md"
    readme.write_text("second commit\n", encoding="utf-8")
    continuous_refactoring.run_command(["git", "add", "README.md"], cwd=repo)
    continuous_refactoring.run_command(["git", "commit", "-m", "second"], cwd=repo)
    assert continuous_refactoring.get_head_sha(repo) != original_head

    readme.write_text("uncommitted\n", encoding="utf-8")
    (repo / "scratch.txt").write_text("scratch\n", encoding="utf-8")

    continuous_refactoring.revert_to(repo, original_head)

    assert continuous_refactoring.get_head_sha(repo) == original_head
    assert readme.read_text(encoding="utf-8") == "seed\n"
    assert not (repo / "scratch.txt").exists()
    assert continuous_refactoring.current_branch(repo) == starting_branch
    assert continuous_refactoring.workspace_status_lines(repo) == []


def test_run_command_checked_failure_raises_git_command_error(tmp_path: Path) -> None:
    command = [
        "python",
        "-c",
        "import sys\nprint('out')\nprint('err', file=sys.stderr)\nraise SystemExit(1)",
    ]

    with pytest.raises(continuous_refactoring.GitCommandError):
        continuous_refactoring.run_command(command, cwd=tmp_path)


def test_run_command_checked_failure_includes_cause_and_payload(tmp_path: Path) -> None:
    command = [
        "python",
        "-c",
        "import sys\nprint('out')\nprint('err', file=sys.stderr)\nraise SystemExit(1)",
    ]

    with pytest.raises(continuous_refactoring.GitCommandError) as exc:
        continuous_refactoring.run_command(command, cwd=tmp_path)

    error = exc.value
    assert isinstance(error.__cause__, subprocess.CalledProcessError)
    assert "command failed (python -c" in str(error)
    assert "stdout:\nout\n" in str(error)
    assert "stderr:\nerr\n" in str(error)


def test_run_command_missing_command_raises_git_command_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def _raise(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("command not found")

    monkeypatch.setattr(subprocess, "run", _raise)

    with pytest.raises(continuous_refactoring.GitCommandError) as exc:
        continuous_refactoring.run_command(["nonexistent-command"], cwd=tmp_path)

    assert isinstance(exc.value.__cause__, FileNotFoundError)


def test_run_command_unchecked_returns_completed_process(tmp_path: Path) -> None:
    command = [
        "python",
        "-c",
        "import sys\nprint('out')\nprint('err', file=sys.stderr)\nraise SystemExit(1)",
    ]

    result = continuous_refactoring.run_command(
        command,
        cwd=tmp_path,
        check=False,
    )

    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode == 1
    assert result.stdout == "out\n"
    assert result.stderr == "err\n"
