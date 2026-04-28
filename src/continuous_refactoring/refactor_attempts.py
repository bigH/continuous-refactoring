from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "_PreservedFile",
    "_PreservedWorkspaceTree",
    "_preserve_workspace_tree",
    "_reset_to_source_baseline",
]

from continuous_refactoring.git import revert_to


@dataclass(frozen=True)
class _PreservedFile:
    relative_path: Path
    content: bytes


@dataclass(frozen=True)
class _PreservedWorkspaceTree:
    files: tuple[_PreservedFile, ...]

    def restore(self, repo_root: Path) -> None:
        for preserved in self.files:
            path = repo_root / preserved.relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(preserved.content)


def _preserve_workspace_tree(
    repo_root: Path,
    root: Path | None,
) -> _PreservedWorkspaceTree | None:
    if root is None:
        return None
    try:
        root.relative_to(repo_root)
    except ValueError:
        return None
    if not root.exists():
        return None

    files = tuple(
        _PreservedFile(path.relative_to(repo_root), path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )
    if not files:
        return None
    return _PreservedWorkspaceTree(files)


def _reset_to_source_baseline(
    repo_root: Path,
    revision: str,
    preserved_workspace: _PreservedWorkspaceTree | None,
) -> None:
    revert_to(repo_root, revision)
    if preserved_workspace is not None:
        preserved_workspace.restore(repo_root)
