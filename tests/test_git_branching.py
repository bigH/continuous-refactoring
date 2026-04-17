from __future__ import annotations

import re
from pathlib import Path

from continuous_refactoring.git import (
    create_branch,
    current_branch,
    checkout_main,
    branch_exists,
    generate_run_branch_name,
    generate_run_once_branch_name,
    get_head_sha,
    prepare_phase_branch,
    prepare_run_branch,
    undo_last_commit,
    run_command,
)


def _init_repo(path: Path, *, branch: str = "main") -> None:
    path.mkdir(parents=True, exist_ok=True)
    run_command(["git", "init", "-b", branch], cwd=path)
    run_command(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path,
    )
    run_command(["git", "config", "user.name", "Test User"], cwd=path)
    (path / "README.md").write_text("seed\n", encoding="utf-8")
    run_command(["git", "add", "README.md"], cwd=path)
    run_command(["git", "commit", "-m", "init"], cwd=path)


# -----------------------------------------------------------------------
# Branch creation
# -----------------------------------------------------------------------


def test_create_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    create_branch(repo, "feature-x")

    assert current_branch(repo) == "feature-x"


# -----------------------------------------------------------------------
# Checkout main detection
# -----------------------------------------------------------------------


def test_checkout_main_detects_main(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, branch="main")

    create_branch(repo, "work")
    assert current_branch(repo) == "work"

    checkout_main(repo)
    assert current_branch(repo) == "main"


def test_checkout_main_detects_master(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, branch="master")

    create_branch(repo, "work")
    assert current_branch(repo) == "work"

    checkout_main(repo)
    assert current_branch(repo) == "master"


def test_prepare_run_branch_reuses_existing_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    create_branch(repo, "my-branch")
    assert current_branch(repo) == "my-branch"

    result = prepare_run_branch(repo, "my-branch", "fallback")

    assert result == "my-branch"
    assert current_branch(repo) == "my-branch"


def test_prepare_phase_branch_reuses_existing_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    create_branch(repo, "phase-branch")
    create_branch(repo, "work")
    assert current_branch(repo) == "work"

    result = prepare_phase_branch(repo, "phase-branch")

    assert result == "phase-branch"
    assert current_branch(repo) == "phase-branch"


def test_prepare_phase_branch_starts_from_main(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    main_head = get_head_sha(repo)

    create_branch(repo, "work")
    (repo / "work.txt").write_text("work\n", encoding="utf-8")
    run_command(["git", "add", "work.txt"], cwd=repo)
    run_command(["git", "commit", "-m", "work change"], cwd=repo)

    result = prepare_phase_branch(repo, "phase-fresh")

    assert result == "phase-fresh"
    assert current_branch(repo) == "phase-fresh"
    assert get_head_sha(repo) == main_head


def test_prepare_run_branch_prefers_requested_name_if_missing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    main_head = get_head_sha(repo)

    result = prepare_run_branch(repo, "does-not-exist", "fallback")

    assert result == "does-not-exist"
    assert current_branch(repo) == "does-not-exist"
    assert get_head_sha(repo) == main_head


# -----------------------------------------------------------------------
# Undo last commit
# -----------------------------------------------------------------------


def test_undo_last_commit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    original_sha = get_head_sha(repo)

    (repo / "extra.txt").write_text("extra\n", encoding="utf-8")
    run_command(["git", "add", "extra.txt"], cwd=repo)
    run_command(["git", "commit", "-m", "add extra"], cwd=repo)
    assert get_head_sha(repo) != original_sha
    assert (repo / "extra.txt").exists()

    undo_last_commit(repo)

    assert get_head_sha(repo) == original_sha
    assert not (repo / "extra.txt").exists()


# -----------------------------------------------------------------------
# Branch name generation
# -----------------------------------------------------------------------


def test_generate_branch_names() -> None:
    run_name = generate_run_branch_name()
    once_name = generate_run_once_branch_name()

    assert re.fullmatch(r"refactor-\d{8}T\d{6}", run_name)
    assert re.fullmatch(r"cr/\d{8}T\d{6}", once_name)


def test_branch_exists_is_literal(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    create_branch(repo, "feature-alpha")

    assert branch_exists(repo, "feature-alpha")
    assert not branch_exists(repo, "feature-*")
