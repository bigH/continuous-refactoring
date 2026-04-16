from __future__ import annotations

import json
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from continuous_refactoring.artifacts import RunArtifacts
    from continuous_refactoring.targeting import Target

__all__ = [
    "ScopeCandidate",
    "ScopeCandidateKind",
    "ScopeSelection",
    "build_scope_candidates",
    "describe_scope_candidate",
    "parse_scope_selection",
    "scope_candidate_to_target",
    "scope_expansion_bypass_reason",
    "select_scope_candidate",
    "write_scope_expansion_artifacts",
]

from continuous_refactoring.agent import maybe_run_agent
from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.prompts import compose_scope_selection_prompt
from continuous_refactoring.targeting import list_tracked_files

ScopeCandidateKind = Literal["seed", "local-cluster", "cross-cluster"]

_SELECTION_RE = re.compile(
    r"^selected-candidate:\s*(seed|local-cluster|cross-cluster)"
    r"(?:\s*[—-]\s*(.+))?$",
    re.IGNORECASE,
)
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
class ScopeSelection:
    kind: ScopeCandidateKind
    reason: str


def scope_expansion_bypass_reason(target: Target) -> str | None:
    if len(target.files) == 0:
        return "scope expansion requires a seed file"
    if len(target.files) > 1 and target.provenance in {"paths", "targets"}:
        return "scope expansion bypassed for explicit multi-file target"
    if len(target.files) != 1:
        return "scope expansion requires a single seed file"
    return None


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


def _paired_source_test_files(seed_file: str, tracked: tuple[str, ...]) -> tuple[str, ...]:
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


def _candidate_validation_surfaces(files: tuple[str, ...], seed_file: str) -> tuple[str, ...]:
    tests = tuple(sorted(file_path for file_path in files if _is_test_file(file_path)))
    return tests or (seed_file,)


def _candidate_from_files(
    kind: ScopeCandidateKind,
    seed_file: str,
    files: tuple[str, ...],
    support: dict[str, tuple[str, ...]],
) -> ScopeCandidate:
    evidence = ["seed target"]
    for file_path in files:
        if file_path == seed_file:
            continue
        evidence.extend(support.get(file_path, ()))
    deduped_evidence = tuple(dict.fromkeys(evidence))
    clusters = tuple(sorted({_cluster_label(path) for path in files}))
    return ScopeCandidate(
        kind=kind,
        files=files,
        cluster_labels=clusters,
        evidence_lines=deduped_evidence,
        validation_surfaces=_candidate_validation_surfaces(files, seed_file),
    )


def _ranked_paths(
    scores: Counter[str],
    support: dict[str, tuple[str, ...]],
    seed_file: str,
    *,
    include_same_dir_cochange_only: bool,
) -> list[str]:
    seed_parent = _cluster_label(seed_file)
    ranked: list[tuple[int, str]] = []
    for path, score in scores.items():
        evidence = support.get(path, ())
        same_dir = _cluster_label(path) == seed_parent
        if (
            same_dir
            and not include_same_dir_cochange_only
            and evidence
            and all(line.startswith("git co-change") for line in evidence)
        ):
            continue
        ranked.append((score, path))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [path for _score, path in ranked]


def _local_ranked_paths(
    scores: Counter[str],
    support: dict[str, tuple[str, ...]],
    seed_file: str,
) -> list[str]:
    seed_parent = _cluster_label(seed_file)
    ranked: list[tuple[int, str]] = []
    for path, score in scores.items():
        evidence = support.get(path, ())
        same_dir = _cluster_label(path) == seed_parent
        has_pairing = any(
            line.startswith("source/test pairing")
            for line in evidence
        )
        has_non_cochange = any(
            not line.startswith("git co-change")
            for line in evidence
        )
        if has_pairing or (same_dir and has_non_cochange):
            ranked.append((score, path))
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

    support_lines: dict[str, list[str]] = defaultdict(list)
    scores: Counter[str] = Counter()

    for paired in _paired_source_test_files(seed_file, tracked):
        support_lines[paired].append(f"source/test pairing with {seed_file}")
        scores[paired] += 50

    for path, alias in _find_direct_references(seed_file, tracked, repo_root).items():
        support_lines[path].append(
            f"direct reference/import-like match from {seed_file}: {alias}"
        )
        scores[path] += 30

    for path, alias in _find_reverse_references(seed_file, tracked, repo_root).items():
        support_lines[path].append(
            f"reverse reference/import-like match to {seed_file}: {alias}"
        )
        scores[path] += 30

    for path, count in _recent_cochange_neighbors(
        seed_file, repo_root, max_commits=max_git_commits,
    ):
        support_lines[path].append(
            f"git co-change with {seed_file}: {count} recent commit(s)"
        )
        scores[path] += min(count, 5) * 5

    support = {
        path: tuple(dict.fromkeys(lines))
        for path, lines in sorted(support_lines.items())
    }

    candidates = [_build_seed_candidate(seed_file)]

    local_ranked = _local_ranked_paths(scores, support, seed_file)
    local_extras = tuple(local_ranked[: max_files - 1])
    if local_extras:
        local_files = (seed_file, *local_extras)
        candidates.append(
            _candidate_from_files("local-cluster", seed_file, local_files, support)
        )

    cross_ranked = _ranked_paths(
        scores,
        support,
        seed_file,
        include_same_dir_cochange_only=False,
    )
    cross_extras = tuple(cross_ranked[: max_files - 1])
    if cross_extras:
        cross_files = (seed_file, *cross_extras)
        cross_candidate = _candidate_from_files(
            "cross-cluster", seed_file, cross_files, support,
        )
        if cross_candidate.files != candidates[-1].files:
            candidates.append(cross_candidate)

    return tuple(candidates[:max_candidates])


def parse_scope_selection(
    stdout: str,
    candidate_kinds: tuple[ScopeCandidateKind, ...],
) -> ScopeSelection:
    last_output_line: str | None = None
    for line in reversed(stdout.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        last_output_line = stripped
        match = _SELECTION_RE.match(stripped)
        if not match:
            continue
        kind = match.group(1).lower()
        if kind not in candidate_kinds:
            raise ContinuousRefactorError(
                f"Selection chose unavailable candidate: {kind!r}"
            )
        reason = match.group(2).strip() if match.group(2) else kind
        return ScopeSelection(kind=kind, reason=reason)
    if last_output_line is None:
        raise ContinuousRefactorError("Scope selection produced no output")
    raise ContinuousRefactorError(
        f"Scope selection produced unrecognised output: {last_output_line!r}"
    )


def scope_candidate_to_target(target: Target, candidate: ScopeCandidate) -> Target:
    return replace(target, files=candidate.files)


def describe_scope_candidate(candidate: ScopeCandidate) -> str:
    sections = [
        f"Selected scope candidate: {candidate.kind}",
        "Files:",
        *(f"- {file_path}" for file_path in candidate.files),
        "Cluster labels:",
        *(f"- {label}" for label in candidate.cluster_labels),
        "Evidence:",
        *(f"- {line}" for line in candidate.evidence_lines),
        "Likely validation surfaces:",
        *(f"- {surface}" for surface in candidate.validation_surfaces),
    ]
    return "\n".join(sections)


def select_scope_candidate(
    target: Target,
    candidates: tuple[ScopeCandidate, ...],
    taste: str,
    repo_root: Path,
    artifacts: RunArtifacts,
    *,
    agent: str,
    model: str,
    effort: str,
    timeout: int | None,
) -> ScopeSelection:
    selection_dir = artifacts.root / "scope-expansion"
    selection_dir.mkdir(parents=True, exist_ok=True)
    selection_stdout_path = selection_dir / "selection.stdout.log"
    selection_last_message_path = selection_dir / "selection-last-message.md"

    if len(candidates) == 1:
        selection = ScopeSelection(
            kind=candidates[0].kind,
            reason="only viable candidate",
        )
        line = f"selected-candidate: {selection.kind} — {selection.reason}\n"
        selection_stdout_path.write_text(line, encoding="utf-8")
        selection_last_message_path.write_text(line, encoding="utf-8")
        return selection

    result = maybe_run_agent(
        agent=agent,
        model=model,
        effort=effort,
        prompt=compose_scope_selection_prompt(target, candidates, taste),
        repo_root=repo_root,
        stdout_path=selection_stdout_path,
        stderr_path=selection_dir / "selection.stderr.log",
        last_message_path=selection_last_message_path if agent == "codex" else None,
        mirror_to_terminal=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise ContinuousRefactorError(
            f"Scope selection agent failed with exit code {result.returncode}"
        )
    candidate_kinds = tuple(candidate.kind for candidate in candidates)
    return parse_scope_selection(result.stdout, candidate_kinds)


def write_scope_expansion_artifacts(
    scope_dir: Path,
    target: Target,
    candidates: tuple[ScopeCandidate, ...],
    *,
    bypass_reason: str | None = None,
    selection: ScopeSelection | None = None,
) -> None:
    scope_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "target": {
            "description": target.description,
            "files": list(target.files),
            "provenance": target.provenance,
        },
        "bypass_reason": bypass_reason,
        "candidates": [asdict(candidate) for candidate in candidates],
    }
    if selection is not None:
        payload["selection"] = asdict(selection)
    (scope_dir / "variants.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
