from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "checkout_main",
    "create_branch",
    "current_branch",
    "detect_main_branch",
    "discard_workspace_changes",
    "generate_run_branch_name",
    "generate_run_once_branch_name",
    "get_head_sha",
    "git_commit",
    "git_push",
    "repo_change_count",
    "repo_has_changes",
    "require_clean_worktree",
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
    run_command(["git", "reset", "--hard", "HEAD"], cwd=repo_root)
    run_command(["git", "clean", "-fd"], cwd=repo_root)


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
    rev = run_command(["git", "rev-parse", "HEAD"], cwd=repo_root).stdout.strip()
    return rev


def git_push(repo_root: Path, remote: str, branch: str) -> None:
    run_command(["git", "push", remote, branch], cwd=repo_root)


def create_branch(repo_root: Path, branch_name: str) -> None:
    """Create and checkout a new branch from current HEAD."""
    run_command(["git", "checkout", "-b", branch_name], cwd=repo_root)


def checkout_main(repo_root: Path) -> None:
    """Checkout main (or master) branch."""
    main_branch = detect_main_branch(repo_root)
    run_command(["git", "checkout", main_branch], cwd=repo_root)


def detect_main_branch(repo_root: Path) -> str:
    """Return 'main' or 'master' based on what exists."""
    result = run_command(
        ["git", "branch", "--list", "main"],
        cwd=repo_root,
        check=False,
    )
    if result.stdout.strip():
        return "main"
    result = run_command(
        ["git", "branch", "--list", "master"],
        cwd=repo_root,
        check=False,
    )
    if result.stdout.strip():
        return "master"
    raise ContinuousRefactorError(
        "Cannot detect main branch (neither 'main' nor 'master' found)"
    )


def undo_last_commit(repo_root: Path) -> None:
    """git reset --soft HEAD~1, then discard_workspace_changes."""
    run_command(["git", "reset", "--soft", "HEAD~1"], cwd=repo_root)
    discard_workspace_changes(repo_root)


def generate_run_branch_name() -> str:
    """'refactor-{timestamp}'"""
    from datetime import datetime

    ts = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")
    return f"refactor-{ts}"


def generate_run_once_branch_name() -> str:
    """'cr/{timestamp}'"""
    from datetime import datetime

    ts = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")
    return f"cr/{ts}"


def get_head_sha(repo_root: Path) -> str:
    """Return current HEAD sha."""
    return run_command(
        ["git", "rev-parse", "HEAD"], cwd=repo_root
    ).stdout.strip()
