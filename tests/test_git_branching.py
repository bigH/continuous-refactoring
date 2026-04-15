from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.agent import run_observed_command
from continuous_refactoring.git import (
    create_branch,
    checkout_main,
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
    subprocess.run(
        ["git", "init", "-b", branch], cwd=path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    (path / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "README.md"], cwd=path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True
    )


def _current_branch(path: Path) -> str:
    return subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


# -----------------------------------------------------------------------
# Branch creation
# -----------------------------------------------------------------------


def test_create_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    create_branch(repo, "feature-x")

    assert _current_branch(repo) == "feature-x"


# -----------------------------------------------------------------------
# Checkout main detection
# -----------------------------------------------------------------------


def test_checkout_main_detects_main(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, branch="main")

    create_branch(repo, "work")
    assert _current_branch(repo) == "work"

    checkout_main(repo)
    assert _current_branch(repo) == "main"


def test_checkout_main_detects_master(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, branch="master")

    create_branch(repo, "work")
    assert _current_branch(repo) == "work"

    checkout_main(repo)
    assert _current_branch(repo) == "master"


def test_prepare_run_branch_reuses_existing_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    create_branch(repo, "my-branch")
    assert _current_branch(repo) == "my-branch"

    result = prepare_run_branch(repo, "my-branch", "fallback")

    assert result == "my-branch"
    assert _current_branch(repo) == "my-branch"


def test_prepare_phase_branch_reuses_existing_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    create_branch(repo, "phase-branch")
    create_branch(repo, "work")
    assert _current_branch(repo) == "work"

    result = prepare_phase_branch(repo, "phase-branch")

    assert result == "phase-branch"
    assert _current_branch(repo) == "phase-branch"


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
    assert _current_branch(repo) == "phase-fresh"
    assert get_head_sha(repo) == main_head


# -----------------------------------------------------------------------
# Undo last commit
# -----------------------------------------------------------------------


def test_undo_last_commit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    original_sha = get_head_sha(repo)

    (repo / "extra.txt").write_text("extra\n", encoding="utf-8")
    subprocess.run(["git", "add", "extra.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add extra"], cwd=repo, check=True, capture_output=True
    )
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


# -----------------------------------------------------------------------
# Timeout
# -----------------------------------------------------------------------


def test_run_observed_command_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pytest

    tmpdir = tmp_path / "tmpdir"
    tmpdir.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmpdir))

    with pytest.raises(ContinuousRefactorError, match="timed out"):
        run_observed_command(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            cwd=tmp_path,
            stdout_path=tmpdir / "out.log",
            stderr_path=tmpdir / "err.log",
            mirror_to_terminal=False,
            timeout=1,
        )


# -----------------------------------------------------------------------
# Integration: branch + commit + undo round-trip
# -----------------------------------------------------------------------


def test_consecutive_failure_tracking(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    original_sha = get_head_sha(repo)

    create_branch(repo, "test-branch")
    assert _current_branch(repo) == "test-branch"

    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    subprocess.run(["git", "add", "change.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "test commit"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    commit_sha = get_head_sha(repo)
    assert commit_sha != original_sha

    undo_last_commit(repo)
    assert get_head_sha(repo) == original_sha
    assert not (repo / "change.txt").exists()


# -----------------------------------------------------------------------
# Stuck-agent detection
# -----------------------------------------------------------------------


def test_agent_killed_when_stdout_stalled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pytest

    tmpdir = tmp_path / "tmpdir"
    tmpdir.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmpdir))

    script = "import sys, time; print('hello'); sys.stdout.flush(); time.sleep(300)"

    with pytest.raises(ContinuousRefactorError, match="no output for"):
        run_observed_command(
            [sys.executable, "-c", script],
            cwd=tmp_path,
            stdout_path=tmpdir / "out.log",
            stderr_path=tmpdir / "err.log",
            mirror_to_terminal=False,
            stuck_interval=1,
            stuck_timeout=2,
        )
