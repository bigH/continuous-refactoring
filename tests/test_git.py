from __future__ import annotations

from pathlib import Path

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
