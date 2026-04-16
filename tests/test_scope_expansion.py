from __future__ import annotations

from pathlib import Path

import continuous_refactoring

from continuous_refactoring.scope_expansion import (
    build_scope_candidates,
    scope_expansion_bypass_reason,
)
from continuous_refactoring.targeting import Target

from conftest import init_repo


def _write(repo_root: Path, relative_path: str, content: str) -> None:
    destination = repo_root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")


def _commit_all(repo_root: Path, message: str) -> None:
    continuous_refactoring.run_command(["git", "add", "-A"], cwd=repo_root)
    continuous_refactoring.run_command(["git", "commit", "-m", message], cwd=repo_root)


def _seed_target(path: str) -> Target:
    return Target(description=path, files=(path,), provenance="globs")


def test_seed_candidate_is_always_present(tmp_path: Path) -> None:
    init_repo(tmp_path)
    _write(tmp_path, "src/foo.py", "VALUE = 1\n")
    _commit_all(tmp_path, "add foo")

    candidates = build_scope_candidates(_seed_target("src/foo.py"), tmp_path)

    assert candidates[0].kind == "seed"
    assert candidates[0].files == ("src/foo.py",)


def test_source_test_pairing_adds_local_cluster(tmp_path: Path) -> None:
    init_repo(tmp_path)
    _write(tmp_path, "src/foo.py", "VALUE = 1\n")
    _write(tmp_path, "tests/test_foo.py", "from src.foo import VALUE\n")
    _commit_all(tmp_path, "add foo and test")

    candidates = build_scope_candidates(_seed_target("src/foo.py"), tmp_path)

    local_cluster = next(
        candidate for candidate in candidates if candidate.kind == "local-cluster"
    )
    assert local_cluster.files == ("src/foo.py", "tests/test_foo.py")


def test_import_like_reference_can_add_local_sibling(tmp_path: Path) -> None:
    init_repo(tmp_path)
    _write(tmp_path, "src/foo.py", "from .helpers import normalize\n")
    _write(tmp_path, "src/helpers.py", "def normalize(value: str) -> str:\n    return value\n")
    _commit_all(tmp_path, "add local siblings")

    candidates = build_scope_candidates(_seed_target("src/foo.py"), tmp_path)

    local_cluster = next(
        candidate for candidate in candidates if candidate.kind == "local-cluster"
    )
    assert local_cluster.files == ("src/foo.py", "src/helpers.py")


def test_git_cochange_neighbors_are_capped_and_deterministic(tmp_path: Path) -> None:
    init_repo(tmp_path)
    _write(tmp_path, "src/foo.py", "VALUE = 0\n")
    for neighbor in ("cross/a.py", "cross/b.py", "cross/c.py", "cross/d.py"):
        _write(tmp_path, neighbor, "VALUE = 0\n")
    _commit_all(tmp_path, "seed files")

    for index, neighbor in enumerate(
        (
            "cross/a.py",
            "cross/a.py",
            "cross/a.py",
            "cross/b.py",
            "cross/b.py",
            "cross/c.py",
            "cross/d.py",
        ),
        start=1,
    ):
        _write(tmp_path, "src/foo.py", f"VALUE = {index}\n")
        _write(tmp_path, neighbor, f"VALUE = {index}\n")
        _commit_all(tmp_path, f"cochange {index}")

    candidates = build_scope_candidates(
        _seed_target("src/foo.py"),
        tmp_path,
        max_files=4,
    )

    cross_cluster = next(
        candidate for candidate in candidates if candidate.kind == "cross-cluster"
    )
    assert cross_cluster.files == (
        "src/foo.py",
        "cross/a.py",
        "cross/b.py",
        "cross/c.py",
    )


def test_explicit_multi_file_targets_bypass_expansion() -> None:
    target = Target(
        description="explicit paths",
        files=("src/foo.py", "src/bar.py"),
        provenance="paths",
    )

    reason = scope_expansion_bypass_reason(target)

    assert reason == "scope expansion bypassed for explicit multi-file target"
