from __future__ import annotations

import json
import random
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from continuous_refactoring.artifacts import ContinuousRefactorError


__all__ = [
    "Target",
    "expand_patterns_to_files",
    "load_targets_jsonl",
    "parse_extensions",
    "parse_globs",
    "resolve_targets",
    "select_random_files",
    "validate_target_line",
]


@dataclass(frozen=True)
class Target:
    description: str
    files: tuple[str, ...]
    scoping: str | None = None
    model_override: str | None = None
    effort_override: str | None = None


def parse_extensions(raw: str) -> tuple[str, ...]:
    """Convert comma-separated extensions to glob patterns.

    ".py,.ts" -> ("**/*.py", "**/*.ts")
    Already-glob inputs (containing '*') pass through unchanged.
    """
    results: list[str] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "*" in part:
            results.append(part)
        else:
            ext = part.lstrip(".")
            results.append(f"**/*.{ext}")
    return tuple(results)


def parse_globs(raw: str) -> tuple[str, ...]:
    """Split colon-separated glob patterns."""
    return tuple(g for g in (p.strip() for p in raw.split(":")) if g)


def validate_target_line(data: dict) -> Target | None:
    """Validate a parsed JSON dict and return a Target, or None if invalid."""
    description = data.get("description")
    if not isinstance(description, str) or not description:
        print("warning: target line has missing or empty description, skipping", file=sys.stderr)
        return None

    files = data.get("files")
    if not isinstance(files, list) or not files:
        print("warning: target line has missing or empty files, skipping", file=sys.stderr)
        return None

    if not all(isinstance(f, str) for f in files):
        print("warning: target line has non-string file entries, skipping", file=sys.stderr)
        return None

    return Target(
        description=description,
        files=tuple(files),
        scoping=data.get("scoping"),
        model_override=data.get("model-override"),
        effort_override=data.get("effort-override"),
    )


def load_targets_jsonl(path: Path) -> list[Target]:
    """Load targets from a JSONL file, skipping invalid lines."""
    targets: list[Target] = []
    for line_num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            print(f"warning: invalid JSON on line {line_num}, skipping", file=sys.stderr)
            continue
        target = validate_target_line(data)
        if target is not None:
            targets.append(target)
    return targets


def _list_tracked_files(repo_root: Path) -> list[str]:
    """Return tracked paths via ``git ls-files -z``.

    Null-delimited output preserves non-ASCII/special-char paths verbatim
    (plain ``git ls-files`` C-quotes them, e.g. ``"caf\\303\\251.py"``, which
    then fails to match any downstream pattern).
    """
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ContinuousRefactorError(
            f"git ls-files failed: {result.stderr.decode('utf-8', 'replace').strip()}"
        )
    return [p.decode("utf-8") for p in result.stdout.split(b"\0") if p]


def select_random_files(repo_root: Path, count: int = 5) -> tuple[str, ...]:
    """Select random tracked files from a git repository."""
    files = _list_tracked_files(repo_root)
    if not files:
        return ()
    return tuple(random.sample(files, min(count, len(files))))


def _compile_glob(pattern: str) -> re.Pattern[str]:
    """Compile a POSIX-style glob; ``*`` matches within a segment, ``**`` crosses segments.

    ``**/`` at the start and ``/**/`` between segments optionally match zero
    segments, so ``**/*.py`` matches ``root.py`` and ``src/**/*.py`` matches
    ``src/foo.py``.
    """
    parts: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i) and (i == 0 or pattern[i - 1] == "/"):
            parts.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            parts.append(".*")
            i += 2
        elif pattern[i] == "*":
            parts.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(parts) + r"\Z")


def expand_patterns_to_files(
    patterns: tuple[str, ...],
    repo_root: Path,
) -> tuple[str, ...]:
    """Return tracked files (relative to ``repo_root``) matching any pattern.

    Uses ``git ls-files -z`` so behavior mirrors :func:`select_random_files`:
    tracked files only, ``.gitignore`` respected, non-ASCII paths preserved.
    Returns a sorted, deduplicated tuple for determinism; sampling happens
    downstream.
    """
    tracked = _list_tracked_files(repo_root)
    if not tracked or not patterns:
        return ()

    compiled = [_compile_glob(p) for p in patterns]
    matched = {f for f in tracked if any(regex.match(f) for regex in compiled)}
    return tuple(sorted(matched))


def _targets_per_file(files: tuple[str, ...]) -> list[Target]:
    return [Target(description=f, files=(f,)) for f in files]


def resolve_targets(
    *,
    extensions: str | None,
    globs: str | None,
    targets_path: Path | None,
    paths: tuple[str, ...] | None,
    repo_root: Path,
) -> list[Target]:
    """Resolve targeting arguments into a list of Targets.

    Priority: targets JSONL > globs > extensions > paths > random from git ls-files.
    Only one source is used (first match in priority order).
    """
    if targets_path is not None:
        return load_targets_jsonl(targets_path)

    if globs is not None:
        patterns = parse_globs(globs)
        return _targets_per_file(expand_patterns_to_files(patterns, repo_root))

    if extensions is not None:
        patterns = parse_extensions(extensions)
        return _targets_per_file(expand_patterns_to_files(patterns, repo_root))

    if paths:
        return [Target(description="specified paths", files=paths)]

    random_files = select_random_files(repo_root)
    if not random_files:
        return []
    return [Target(description="random files", files=random_files)]
