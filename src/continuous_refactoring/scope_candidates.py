from __future__ import annotations

import re
import subprocess
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from continuous_refactoring.targeting import Target

__all__ = [
    "ScopeCandidate",
    "ScopeCandidateKind",
    "build_scope_candidates",
]

from continuous_refactoring.targeting import list_tracked_files

ScopeCandidateKind = Literal["seed", "local-cluster", "cross-cluster"]
_SupportKind = Literal["source-test-pairing", "direct-reference", "reverse-reference", "git-cochange"]

_IDENTIFIER_BOUNDARY = r"[A-Za-z0-9_]"
_COMMON_STEMS = {"__init__", "index", "main", "test"}


@dataclass(frozen=True)
class ScopeCandidate:
    kind: ScopeCandidateKind
    files: tuple[str, ...]
    cluster_labels: tuple[str, ...]
    evidence_lines: tuple[str, ...]
    validation_surfaces: tuple[str, ...]


@dataclass(frozen=True)
class _CandidateSupport:
    scores: dict[str, int]
    evidence: dict[str, tuple[str, ...]]
    support_kinds: dict[str, tuple[_SupportKind, ...]]


def _is_test_file(path: str) -> bool:
    pure = PurePosixPath(path)
    stem = pure.stem
    return (
        "tests" in pure.parts
        or pure.name.startswith("test_")
        or stem.endswith("_test")
    )


def _normalized_test_stem(path: str) -> str:
    stem = PurePosixPath(path).stem
    if stem.startswith("test_"):
        return stem.removeprefix("test_")
    if stem.endswith("_test"):
        return stem.removesuffix("_test")
    return stem


def _cluster_label(path: str) -> str:
    parent = PurePosixPath(path).parent.as_posix()
    return "." if parent == "." else parent


def _reference_aliases(path: str) -> tuple[str, ...]:
    pure = PurePosixPath(path)
    no_ext_parts = pure.with_suffix("").parts
    aliases = {path, pure.name}

    stem = pure.stem
    if len(stem) >= 3 and stem not in _COMMON_STEMS:
        aliases.add(stem)

    dotted_full = ".".join(no_ext_parts)
    if dotted_full:
        aliases.add(dotted_full)

    if no_ext_parts and no_ext_parts[0] in {"src", "lib", "app", "tests", "test"}:
        shortened = ".".join(no_ext_parts[1:])
        if shortened:
            aliases.add(shortened)

    if len(no_ext_parts) >= 2:
        aliases.add("/".join(no_ext_parts[-2:]))
        aliases.add(".".join(no_ext_parts[-2:]))

    return tuple(sorted(aliases, key=lambda alias: (-len(alias), alias)))


def _text_mentions_alias(text: str, alias: str) -> bool:
    if not alias:
        return False
    pattern = re.compile(
        rf"(?<!{_IDENTIFIER_BOUNDARY}){re.escape(alias)}(?!{_IDENTIFIER_BOUNDARY})"
    )
    return pattern.search(text) is not None


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        return ""


def _paired_source_test_files(
    seed_file: str,
    tracked: tuple[str, ...],
) -> tuple[str, ...]:
    seed_is_test = _is_test_file(seed_file)
    seed_stem = (
        _normalized_test_stem(seed_file)
        if seed_is_test
        else PurePosixPath(seed_file).stem
    )
    paired: list[str] = []
    for path in tracked:
        if path == seed_file:
            continue
        path_is_test = _is_test_file(path)
        if seed_is_test == path_is_test:
            continue
        compare_stem = (
            _normalized_test_stem(path)
            if path_is_test
            else PurePosixPath(path).stem
        )
        if compare_stem == seed_stem:
            paired.append(path)
    return tuple(sorted(paired))


def _find_direct_references(
    seed_file: str,
    tracked: tuple[str, ...],
    repo_root: Path,
) -> dict[str, str]:
    text = _safe_read_text(repo_root / seed_file)
    if not text:
        return {}

    matches: dict[str, str] = {}
    for path in tracked:
        if path == seed_file:
            continue
        for alias in _reference_aliases(path):
            if _text_mentions_alias(text, alias):
                matches[path] = alias
                break
    return matches


def _find_reverse_references(
    seed_file: str,
    tracked: tuple[str, ...],
    repo_root: Path,
) -> dict[str, str]:
    seed_aliases = _reference_aliases(seed_file)
    matches: dict[str, str] = {}
    for path in tracked:
        if path == seed_file:
            continue
        text = _safe_read_text(repo_root / path)
        if not text:
            continue
        for alias in seed_aliases:
            if _text_mentions_alias(text, alias):
                matches[path] = alias
                break
    return matches


def _recent_cochange_neighbors(
    seed_file: str,
    repo_root: Path,
    *,
    max_commits: int,
) -> tuple[tuple[str, int], ...]:
    log_result = subprocess.run(
        ["git", "log", "--format=%H", f"--max-count={max_commits}", "--", seed_file],
        cwd=repo_root,
        capture_output=True,
        check=False,
        text=True,
    )
    if log_result.returncode != 0:
        return ()

    counts: Counter[str] = Counter()
    commits = [line.strip() for line in log_result.stdout.splitlines() if line.strip()]
    for commit in commits:
        show_result = subprocess.run(
            ["git", "show", "--format=", "--name-only", commit],
            cwd=repo_root,
            capture_output=True,
            check=False,
            text=True,
        )
        if show_result.returncode != 0:
            continue
        files = {
            line.strip()
            for line in show_result.stdout.splitlines()
            if line.strip() and line.strip() != seed_file
        }
        for path in files:
            counts[path] += 1
    return tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _build_seed_candidate(seed_file: str) -> ScopeCandidate:
    return ScopeCandidate(
        kind="seed",
        files=(seed_file,),
        cluster_labels=(_cluster_label(seed_file),),
        evidence_lines=("seed target",),
        validation_surfaces=(seed_file,),
    )


def _candidate_validation_surfaces(
    files: tuple[str, ...],
    seed_file: str,
) -> tuple[str, ...]:
    tests = tuple(sorted(file_path for file_path in files if _is_test_file(file_path)))
    return tests or (seed_file,)


def _candidate_from_files(
    kind: ScopeCandidateKind,
    seed_file: str,
    files: tuple[str, ...],
    evidence_by_file: dict[str, tuple[str, ...]],
) -> ScopeCandidate:
    evidence = ["seed target"]
    for file_path in files:
        if file_path == seed_file:
            continue
        evidence.extend(evidence_by_file.get(file_path, ()))
    deduped_evidence = tuple(dict.fromkeys(evidence))
    clusters = tuple(sorted({_cluster_label(path) for path in files}))
    return ScopeCandidate(
        kind=kind,
        files=files,
        cluster_labels=clusters,
        evidence_lines=deduped_evidence,
        validation_surfaces=_candidate_validation_surfaces(files, seed_file),
    )


def _record_support(
    support_lines: dict[str, list[str]],
    support_kinds: dict[str, list[_SupportKind]],
    scores: Counter[str],
    file_path: str,
    support_kind: _SupportKind,
    evidence_line: str,
    score: int,
) -> None:
    support_lines[file_path].append(evidence_line)
    support_kinds[file_path].append(support_kind)
    scores[file_path] += score


def _candidate_support(
    seed_file: str,
    tracked: tuple[str, ...],
    repo_root: Path,
    *,
    max_git_commits: int,
) -> _CandidateSupport:
    support_lines: dict[str, list[str]] = defaultdict(list)
    support_kinds: dict[str, list[_SupportKind]] = defaultdict(list)
    scores: Counter[str] = Counter()

    for paired in _paired_source_test_files(seed_file, tracked):
        _record_support(
            support_lines,
            support_kinds,
            scores,
            paired,
            "source-test-pairing",
            f"source/test pairing with {seed_file}",
            50,
        )

    for path, alias in _find_direct_references(seed_file, tracked, repo_root).items():
        _record_support(
            support_lines,
            support_kinds,
            scores,
            path,
            "direct-reference",
            f"direct reference/import-like match from {seed_file}: {alias}",
            30,
        )

    for path, alias in _find_reverse_references(seed_file, tracked, repo_root).items():
        _record_support(
            support_lines,
            support_kinds,
            scores,
            path,
            "reverse-reference",
            f"reverse reference/import-like match to {seed_file}: {alias}",
            30,
        )

    for path, count in _recent_cochange_neighbors(
        seed_file, repo_root, max_commits=max_git_commits,
    ):
        _record_support(
            support_lines,
            support_kinds,
            scores,
            path,
            "git-cochange",
            f"git co-change with {seed_file}: {count} recent commit(s)",
            min(count, 5) * 5,
        )

    return _CandidateSupport(
        scores=dict(sorted(scores.items())),
        evidence={
            path: tuple(dict.fromkeys(lines))
            for path, lines in sorted(support_lines.items())
        },
        support_kinds={
            path: tuple(dict.fromkeys(kinds))
            for path, kinds in sorted(support_kinds.items())
        },
    )


def _rank_paths(
    scores: dict[str, int],
    support_kinds_by_file: dict[str, tuple[_SupportKind, ...]],
    seed_file: str,
    include: Callable[[bool, tuple[_SupportKind, ...]], bool],
) -> list[str]:
    seed_parent = _cluster_label(seed_file)
    ranked = [
        (score, path)
        for path, score in scores.items()
        if include(
            _cluster_label(path) == seed_parent,
            support_kinds_by_file.get(path, ()),
        )
    ]
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [path for _score, path in ranked]


def build_scope_candidates(
    target: Target,
    repo_root: Path,
    *,
    max_candidates: int = 3,
    max_files: int = 8,
    max_git_commits: int = 20,
) -> tuple[ScopeCandidate, ...]:
    if max_candidates < 1:
        raise ValueError("max_candidates must be >= 1")
    if max_files < 1:
        raise ValueError("max_files must be >= 1")

    seed_file = target.files[0]
    tracked = tuple(sorted(list_tracked_files(repo_root)))
    if seed_file not in tracked:
        return (_build_seed_candidate(seed_file),)

    support = _candidate_support(
        seed_file, tracked, repo_root, max_git_commits=max_git_commits,
    )
    candidates = [_build_seed_candidate(seed_file)]

    def include_local(same_dir: bool, support_kinds: tuple[_SupportKind, ...]) -> bool:
        return "source-test-pairing" in support_kinds or (
            same_dir and any(kind != "git-cochange" for kind in support_kinds)
        )

    def include_cross(same_dir: bool, support_kinds: tuple[_SupportKind, ...]) -> bool:
        return not (
            same_dir
            and support_kinds
            and all(kind == "git-cochange" for kind in support_kinds)
        )

    local_ranked = _rank_paths(
        support.scores,
        support.support_kinds,
        seed_file,
        include_local,
    )
    local_extras = tuple(local_ranked[: max_files - 1])
    if local_extras:
        local_files = (seed_file, *local_extras)
        candidates.append(
            _candidate_from_files(
                "local-cluster", seed_file, local_files, support.evidence,
            )
        )

    cross_ranked = _rank_paths(
        support.scores,
        support.support_kinds,
        seed_file,
        include_cross,
    )
    cross_extras = tuple(cross_ranked[: max_files - 1])
    if cross_extras:
        cross_files = (seed_file, *cross_extras)
        cross_candidate = _candidate_from_files(
            "cross-cluster", seed_file, cross_files, support.evidence,
        )
        if cross_candidate.files != candidates[-1].files:
            candidates.append(cross_candidate)

    return tuple(candidates[:max_candidates])
