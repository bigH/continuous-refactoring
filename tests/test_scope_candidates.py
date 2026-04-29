from __future__ import annotations

from pathlib import Path

import continuous_refactoring

from conftest import init_repo
from continuous_refactoring.scope_candidates import (
    build_scope_candidates,
)
from continuous_refactoring.targeting import Target


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


def test_untracked_seed_returns_only_seed_candidate(tmp_path: Path) -> None:
    init_repo(tmp_path)
    _write(tmp_path, "src/foo.py", "VALUE = 1\n")

    candidates = build_scope_candidates(_seed_target("src/foo.py"), tmp_path)

    assert [candidate.kind for candidate in candidates] == ["seed"]
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


def test_reverse_reference_can_add_local_sibling(tmp_path: Path) -> None:
    init_repo(tmp_path)
    _write(tmp_path, "src/foo.py", "VALUE = 1\n")
    _write(tmp_path, "src/consumer.py", "from .foo import VALUE\n")
    _commit_all(tmp_path, "add local reverse reference")

    candidates = build_scope_candidates(_seed_target("src/foo.py"), tmp_path)

    local_cluster = next(
        candidate for candidate in candidates if candidate.kind == "local-cluster"
    )
    assert local_cluster.files == ("src/foo.py", "src/consumer.py")
    assert (
        "reverse reference/import-like match to src/foo.py: foo"
        in local_cluster.evidence_lines
    )


def test_local_git_cochange_alone_does_not_add_noisy_local_sibling(
    tmp_path: Path,
) -> None:
    init_repo(tmp_path)
    _write(tmp_path, "src/foo.py", "VALUE = 0\n")
    _write(tmp_path, "src/helpers.py", "VALUE = 0\n")
    _commit_all(tmp_path, "seed files")

    _write(tmp_path, "src/foo.py", "VALUE = 1\n")
    _write(tmp_path, "src/helpers.py", "VALUE = 1\n")
    _commit_all(tmp_path, "local cochange")

    candidates = build_scope_candidates(_seed_target("src/foo.py"), tmp_path)

    assert [candidate.kind for candidate in candidates] == ["seed"]


def test_cross_cluster_excludes_same_dir_git_only_noise(
    tmp_path: Path,
) -> None:
    init_repo(tmp_path)
    _write(tmp_path, "src/foo.py", "VALUE = 0\n")
    _write(tmp_path, "src/helpers.py", "VALUE = 0\n")
    _write(tmp_path, "cross/a.py", "VALUE = 0\n")
    _commit_all(tmp_path, "seed files")

    _write(tmp_path, "src/foo.py", "VALUE = 1\n")
    _write(tmp_path, "src/helpers.py", "VALUE = 1\n")
    _write(tmp_path, "cross/a.py", "VALUE = 1\n")
    _commit_all(tmp_path, "mixed cochange")

    candidates = build_scope_candidates(_seed_target("src/foo.py"), tmp_path)

    cross_cluster = next(
        candidate for candidate in candidates if candidate.kind == "cross-cluster"
    )
    assert cross_cluster.files == ("src/foo.py", "cross/a.py")


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


def test_max_candidates_prunes_without_dropping_seed_candidate(tmp_path: Path) -> None:
    init_repo(tmp_path)
    _write(tmp_path, "src/foo.py", "VALUE = 0\n")
    _write(tmp_path, "tests/test_foo.py", "from src.foo import VALUE\n")
    _write(tmp_path, "cross/a.py", "VALUE = 0\n")
    _commit_all(tmp_path, "seed files")

    _write(tmp_path, "src/foo.py", "VALUE = 1\n")
    _write(tmp_path, "cross/a.py", "VALUE = 1\n")
    _commit_all(tmp_path, "cross cochange")

    uncapped_candidates = build_scope_candidates(_seed_target("src/foo.py"), tmp_path)
    capped_candidates = build_scope_candidates(
        _seed_target("src/foo.py"),
        tmp_path,
        max_candidates=2,
    )

    assert [candidate.kind for candidate in uncapped_candidates] == [
        "seed",
        "local-cluster",
        "cross-cluster",
    ]
    assert [candidate.kind for candidate in capped_candidates] == [
        "seed",
        "local-cluster",
    ]
