from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "current_branch",
    "discard_workspace_changes",
    "get_head_sha",
    "git_commit",
    "repo_change_count",
    "repo_has_changes",
    "require_clean_worktree",
    "revert_to",
    "run_command",
    "undo_last_commit",
    "workspace_status_lines",
]

from continuous_refactoring.artifacts import ContinuousRefactorError


def run_command(
    command: Sequence[str],
    cwd: Path,
    *,
    check: bool = True,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        shell=False,
        check=False,
        capture_output=capture_output,
    )
    if check and proc.returncode != 0:
        raise ContinuousRefactorError(
            f"command failed ({' '.join(command)})\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc


def workspace_status_lines(repo_root: Path) -> list[str]:
    result = run_command(["git", "status", "--porcelain"], cwd=repo_root, check=False)
    return [line for line in result.stdout.splitlines() if line.strip()]


def require_clean_worktree(repo_root: Path) -> None:
    status_lines = workspace_status_lines(repo_root)
    if not status_lines:
        return
    status = "\n".join(status_lines)
    raise ContinuousRefactorError(
        "Aborting: working copy has local changes before continuous refactoring "
        "starts.\n"
        "Commit, stash, or discard these changes first:\n"
        f"{status}"
    )


def discard_workspace_changes(repo_root: Path) -> None:
    _reset_hard_and_clean(repo_root, "HEAD")


def repo_change_count(repo_root: Path) -> int:
    return len(workspace_status_lines(repo_root))


def repo_has_changes(repo_root: Path) -> bool:
    return repo_change_count(repo_root) > 0


def current_branch(repo_root: Path) -> str:
    result = run_command(
        ["git", "branch", "--show-current"],
        cwd=repo_root,
        check=False,
    )
    branch = result.stdout.strip()
    if not branch:
        raise ContinuousRefactorError(
            "Cannot determine current git branch; are you on a detached HEAD?"
        )
    return branch


def git_commit(repo_root: Path, message: str) -> str:
    run_command(["git", "add", "-A"], cwd=repo_root)
    if not repo_has_changes(repo_root):
        raise ContinuousRefactorError("No changes to commit.")
    run_command(["git", "commit", "-m", message], cwd=repo_root)
    return get_head_sha(repo_root)


def undo_last_commit(repo_root: Path) -> None:
    run_command(["git", "reset", "--soft", "HEAD~1"], cwd=repo_root)
    discard_workspace_changes(repo_root)


def revert_to(repo_root: Path, expected_head: str) -> None:
    _reset_hard_and_clean(repo_root, expected_head)


def get_head_sha(repo_root: Path) -> str:
    return run_command(
        ["git", "rev-parse", "HEAD"], cwd=repo_root
    ).stdout.strip()


def _reset_hard_and_clean(repo_root: Path, revision: str) -> None:
    run_command(["git", "reset", "--hard", revision], cwd=repo_root)
    run_command(["git", "clean", "-fd"], cwd=repo_root)
