from __future__ import annotations

import json
import random
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Target:
    description: str
    files: tuple[str, ...]
    scoping: str | None
    model_override: str | None
    effort_override: str | None


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


def parse_paths(raw: str) -> tuple[str, ...]:
    """Split colon-separated file paths."""
    return tuple(p for p in (s.strip() for s in raw.split(":")) if p)


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


def select_random_files(repo_root: Path, count: int = 5) -> tuple[str, ...]:
    """Select random tracked files from a git repository."""
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    files = [f for f in result.stdout.splitlines() if f.strip()]
    if not files:
        return ()
    return tuple(random.sample(files, min(count, len(files))))


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
        return [Target(
            description="glob patterns",
            files=parse_globs(globs),
            scoping=None,
            model_override=None,
            effort_override=None,
        )]

    if extensions is not None:
        return [Target(
            description="file extensions",
            files=parse_extensions(extensions),
            scoping=None,
            model_override=None,
            effort_override=None,
        )]

    if paths:
        return [Target(
            description="specified paths",
            files=paths,
            scoping=None,
            model_override=None,
            effort_override=None,
        )]

    random_files = select_random_files(repo_root)
    if not random_files:
        return []
    return [Target(
        description="random files",
        files=random_files,
        scoping=None,
        model_override=None,
        effort_override=None,
    )]
