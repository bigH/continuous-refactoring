from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "branch_exists",
    "checkout_branch",
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
    "prepare_phase_branch",
    "prepare_run_branch",
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
    return get_head_sha(repo_root)


def git_push(repo_root: Path, remote: str, branch: str) -> None:
    run_command(["git", "push", remote, branch], cwd=repo_root)


def create_branch(repo_root: Path, branch_name: str) -> None:
    run_command(["git", "checkout", "-b", branch_name], cwd=repo_root)


def checkout_branch(repo_root: Path, branch_name: str) -> None:
    run_command(["git", "checkout", branch_name], cwd=repo_root)


def branch_exists(repo_root: Path, branch_name: str) -> bool:
    result = run_command(
        ["git", "branch", "--list", branch_name],
        cwd=repo_root,
        check=False,
    )
    return bool(result.stdout.strip())


def prepare_run_branch(
    repo_root: Path,
    use_branch: str | None,
    default_name: str,
) -> str:
    if use_branch and branch_exists(repo_root, use_branch):
        checkout_branch(repo_root, use_branch)
        return use_branch
    checkout_main(repo_root)
    return _create_or_checkout_branch(repo_root, use_branch or default_name)


def prepare_phase_branch(repo_root: Path, branch_name: str) -> str:
    checkout_main(repo_root)
    return _create_or_checkout_branch(repo_root, branch_name)


def _create_or_checkout_branch(repo_root: Path, branch_name: str) -> str:
    if branch_exists(repo_root, branch_name):
        checkout_branch(repo_root, branch_name)
    else:
        create_branch(repo_root, branch_name)
    return branch_name


def checkout_main(repo_root: Path) -> None:
    main_branch = detect_main_branch(repo_root)
    run_command(["git", "checkout", main_branch], cwd=repo_root)


def detect_main_branch(repo_root: Path) -> str:
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
    run_command(["git", "reset", "--soft", "HEAD~1"], cwd=repo_root)
    discard_workspace_changes(repo_root)


def revert_to(repo_root: Path, expected_head: str) -> None:
    if get_head_sha(repo_root) != expected_head:
        undo_last_commit(repo_root)
    else:
        discard_workspace_changes(repo_root)


def generate_run_branch_name() -> str:
    return f"refactor-{_local_timestamp()}"


def generate_run_once_branch_name() -> str:
    return f"cr/{_local_timestamp()}"


def get_head_sha(repo_root: Path) -> str:
    return run_command(
        ["git", "rev-parse", "HEAD"], cwd=repo_root
    ).stdout.strip()


def _local_timestamp() -> str:
    from datetime import datetime

    return datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")
