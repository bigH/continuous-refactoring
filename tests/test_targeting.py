from __future__ import annotations

import json
import random
import subprocess
import uuid
from pathlib import Path

from continuous_refactoring.targeting import (
    Target,
    expand_patterns_to_files,
    load_targets_jsonl,
    parse_extensions,
    parse_globs,
    resolve_targets,
    select_random_files,
    validate_target_line,
)


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=path, check=True, capture_output=True,
    )
    (path / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True,
    )


def _repo_with_files(path: Path) -> None:
    """Create a git repo with known source files."""
    _init_repo(path)
    (path / "src").mkdir(parents=True, exist_ok=True)
    (path / "src" / "foo.py").write_text("# foo\n")
    (path / "src" / "bar.py").write_text("# bar\n")
    (path / "tests").mkdir(parents=True, exist_ok=True)
    (path / "tests" / "test_foo.py").write_text("# test\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add files"],
        cwd=path, check=True, capture_output=True,
    )


# ---------------------------------------------------------------------------
# parse_extensions
# ---------------------------------------------------------------------------

def test_parse_extensions_basic() -> None:
    assert parse_extensions(".py,.ts") == ("**/*.py", "**/*.ts")


def test_parse_extensions_with_spaces() -> None:
    assert parse_extensions(" .py , .ts ") == ("**/*.py", "**/*.ts")


def test_parse_extensions_already_glob() -> None:
    assert parse_extensions("**/*.py") == ("**/*.py",)


# ---------------------------------------------------------------------------
# parse_globs
# ---------------------------------------------------------------------------

def test_parse_globs_colon_separated() -> None:
    assert parse_globs("src/**/*.py:tests/**/*.py") == (
        "src/**/*.py",
        "tests/**/*.py",
    )


# ---------------------------------------------------------------------------
# load_targets_jsonl
# ---------------------------------------------------------------------------

def test_load_targets_jsonl_valid(tmp_path: Path) -> None:
    jsonl = tmp_path / "targets.jsonl"
    lines = [
        json.dumps({"description": "Python files", "files": ["**/*.py"]}),
        json.dumps({"description": "TS files", "files": ["**/*.ts"], "scoping": "only utils"}),
    ]
    jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")

    targets = load_targets_jsonl(jsonl)

    assert len(targets) == 2
    assert targets[0] == Target(
        description="Python files",
        files=("**/*.py",),
        scoping=None,
        model_override=None,
        effort_override=None,
    )
    assert targets[1].scoping == "only utils"


def test_load_targets_jsonl_skips_invalid(tmp_path: Path, capsys) -> None:
    jsonl = tmp_path / "targets.jsonl"
    lines = [
        json.dumps({"description": "good", "files": ["*.py"]}),
        "not valid json",
        json.dumps({"description": "also good", "files": ["*.ts"]}),
    ]
    jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")

    targets = load_targets_jsonl(jsonl)

    assert len(targets) == 2
    captured = capsys.readouterr()
    assert "invalid JSON" in captured.err


def test_load_targets_jsonl_skips_non_dict_lines(tmp_path: Path, capsys) -> None:
    jsonl = tmp_path / "targets.jsonl"
    lines = [
        json.dumps({"description": "good", "files": ["*.py"]}),
        "123",
        "true",
        "null",
        json.dumps({"description": "also good", "files": ["*.ts"]}),
    ]
    jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")

    targets = load_targets_jsonl(jsonl)

    assert len(targets) == 2
    captured = capsys.readouterr()
    assert "non-dict target data" in captured.err


def test_load_targets_jsonl_empty_description_skipped(tmp_path: Path, capsys) -> None:
    jsonl = tmp_path / "targets.jsonl"
    jsonl.write_text(
        json.dumps({"description": "", "files": ["x"]}) + "\n",
        encoding="utf-8",
    )

    targets = load_targets_jsonl(jsonl)

    assert targets == []
    captured = capsys.readouterr()
    assert "empty description" in captured.err


def test_load_targets_jsonl_empty_files_skipped(tmp_path: Path, capsys) -> None:
    jsonl = tmp_path / "targets.jsonl"
    jsonl.write_text(
        json.dumps({"description": "x", "files": []}) + "\n",
        encoding="utf-8",
    )

    targets = load_targets_jsonl(jsonl)

    assert targets == []
    captured = capsys.readouterr()
    assert "empty files" in captured.err


def test_load_targets_jsonl_extra_fields_ignored(tmp_path: Path) -> None:
    jsonl = tmp_path / "targets.jsonl"
    data = {"description": "test", "files": ["*.py"], "unknown_field": 42, "another": True}
    jsonl.write_text(json.dumps(data) + "\n", encoding="utf-8")

    targets = load_targets_jsonl(jsonl)

    assert len(targets) == 1
    assert targets[0].description == "test"


def test_load_targets_jsonl_optional_fields(tmp_path: Path) -> None:
    jsonl = tmp_path / "targets.jsonl"
    data = {"description": "minimal", "files": ["*.py"]}
    jsonl.write_text(json.dumps(data) + "\n", encoding="utf-8")

    targets = load_targets_jsonl(jsonl)

    assert len(targets) == 1
    t = targets[0]
    assert t.scoping is None
    assert t.model_override is None
    assert t.effort_override is None


# ---------------------------------------------------------------------------
# validate_target_line
# ---------------------------------------------------------------------------

def test_validate_target_line_all_fields() -> None:
    data = {
        "description": "full target",
        "files": ["src/**/*.py", "lib/**/*.py"],
        "scoping": "focus on error handling",
        "model-override": "claude-opus-4-20250514",
        "effort-override": "high",
    }
    target = validate_target_line(data)

    assert target is not None
    assert target.description == "full target"
    assert target.files == ("src/**/*.py", "lib/**/*.py")
    assert target.scoping == "focus on error handling"
    assert target.model_override == "claude-opus-4-20250514"
    assert target.effort_override == "high"


def test_validate_target_line_rejects_empty_and_invalid_optional_fields() -> None:
    target = validate_target_line(
        {
            "description": "  ",
            "files": ["src/**/*.py"],
            "scoping": None,
        },
    )
    assert target is None

    target = validate_target_line(
        {
            "description": "good",
            "files": [""],
        },
    )
    assert target is None

    target = validate_target_line(
        {
            "description": "good",
            "files": ["src/**/*.py"],
            "model-override": 123,
        },
    )
    assert target is None

    target = validate_target_line(
        {
            "description": "good",
            "files": ["src/**/*.py"],
            "effort-override": "   ",
        },
    )
    assert target is None


def test_load_targets_jsonl_skips_invalid_optional_fields(tmp_path: Path, capsys) -> None:
    jsonl = tmp_path / "targets.jsonl"
    lines = [
        json.dumps({"description": "good", "files": ["*.py"]}),
        json.dumps({"description": "bad", "files": ["*.py"], "model-override": 99}),
        json.dumps({"description": "also good", "files": ["*.ts"]}),
    ]
    jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")

    targets = load_targets_jsonl(jsonl)

    assert len(targets) == 2
    captured = capsys.readouterr()
    assert "model-override" in captured.err


# ---------------------------------------------------------------------------
# select_random_files
# ---------------------------------------------------------------------------

def test_select_random_files_from_git(tmp_path: Path) -> None:
    _repo_with_files(tmp_path)

    selected = select_random_files(tmp_path)

    all_tracked = {"README.md", "src/foo.py", "src/bar.py", "tests/test_foo.py"}
    assert set(selected).issubset(all_tracked)
    assert len(selected) > 0


def test_select_random_files_respects_count(tmp_path: Path) -> None:
    _repo_with_files(tmp_path)

    selected = select_random_files(tmp_path, count=2)

    assert len(selected) == 2


# ---------------------------------------------------------------------------
# resolve_targets
# ---------------------------------------------------------------------------

def test_resolve_targets_prefers_jsonl(tmp_path: Path) -> None:
    _repo_with_files(tmp_path)
    jsonl = tmp_path / "targets.jsonl"
    jsonl.write_text(
        json.dumps({"description": "jsonl wins", "files": ["*.jsonl"]}) + "\n",
        encoding="utf-8",
    )

    targets = resolve_targets(
        extensions=".py",
        globs="src/**/*.py",
        targets_path=jsonl,
        paths=("src/foo.py",),
        repo_root=tmp_path,
    )

    assert len(targets) == 1
    assert targets[0].description == "jsonl wins"


def test_resolve_targets_prefers_globs_over_extensions(tmp_path: Path) -> None:
    _repo_with_files(tmp_path)

    targets = resolve_targets(
        extensions=".py",
        globs="src/**/*.py",
        targets_path=None,
        paths=None,
        repo_root=tmp_path,
    )

    # Globs branch wins over extensions and returns one Target per matched file.
    assert len(targets) == 2
    assert all(len(t.files) == 1 for t in targets)
    files = [t.files[0] for t in targets]
    assert files == sorted(files)
    assert set(files) == {"src/foo.py", "src/bar.py"}
    for target in targets:
        assert target.description == target.files[0]


def test_resolve_targets_extensions_expands_to_one_target_per_file(tmp_path: Path) -> None:
    _repo_with_files(tmp_path)

    targets = resolve_targets(
        extensions=".py",
        globs=None,
        targets_path=None,
        paths=None,
        repo_root=tmp_path,
    )

    assert len(targets) == 3
    assert all(len(t.files) == 1 for t in targets)
    assert all(t.description == t.files[0] for t in targets)
    files = [t.files[0] for t in targets]
    assert files == sorted(files)
    assert set(files) == {"src/foo.py", "src/bar.py", "tests/test_foo.py"}


def test_resolve_targets_globs_dedupe(tmp_path: Path) -> None:
    _repo_with_files(tmp_path)

    targets = resolve_targets(
        extensions=None,
        globs="src/**/*.py:src/foo.py",
        targets_path=None,
        paths=None,
        repo_root=tmp_path,
    )

    files = [t.files[0] for t in targets]
    assert files.count("src/foo.py") == 1
    assert set(files) == {"src/foo.py", "src/bar.py"}


def test_resolve_targets_extensions_no_match_returns_empty(tmp_path: Path) -> None:
    _repo_with_files(tmp_path)

    targets = resolve_targets(
        extensions=".rs",
        globs=None,
        targets_path=None,
        paths=None,
        repo_root=tmp_path,
    )

    assert targets == []


def test_expand_patterns_handles_recursive_glob(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "deep" / "nested").mkdir(parents=True)
    (tmp_path / "deep" / "nested" / "a.py").write_text("# deep\n")
    (tmp_path / "root.py").write_text("# root\n")
    (tmp_path / "note.md").write_text("md\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "deep"],
        cwd=tmp_path, check=True, capture_output=True,
    )

    files = expand_patterns_to_files(("**/*.py",), tmp_path)

    assert files == ("deep/nested/a.py", "root.py")


def test_expand_patterns_returns_sorted_deduplicated(tmp_path: Path) -> None:
    _repo_with_files(tmp_path)

    files = expand_patterns_to_files(("**/*.py", "src/foo.py"), tmp_path)

    assert files == ("src/bar.py", "src/foo.py", "tests/test_foo.py")


def test_expand_patterns_empty_patterns_returns_empty(tmp_path: Path) -> None:
    _repo_with_files(tmp_path)

    assert expand_patterns_to_files((), tmp_path) == ()


def test_expand_patterns_matches_non_ascii_filenames(tmp_path: Path) -> None:
    """Without ``git ls-files -z``, paths with non-ASCII bytes get C-quoted
    (e.g. ``"caf\\303\\251.py"``) and never match a glob.
    """
    _init_repo(tmp_path)
    (tmp_path / "r\u00e9sum\u00e9.py").write_text("# accent\n", encoding="utf-8")
    (tmp_path / "caf\u00e9.py").write_text("# accent\n", encoding="utf-8")
    (tmp_path / "plain.py").write_text("# plain\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "unicode"],
        cwd=tmp_path, check=True, capture_output=True,
    )

    files = expand_patterns_to_files(("**/*.py",), tmp_path)

    assert "r\u00e9sum\u00e9.py" in files
    assert "caf\u00e9.py" in files
    assert "plain.py" in files


def test_select_random_files_handles_non_ascii_filenames(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "caf\u00e9.py").write_text("# accent\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "unicode"],
        cwd=tmp_path, check=True, capture_output=True,
    )

    selected = select_random_files(tmp_path)

    assert "caf\u00e9.py" in selected


def test_expand_patterns_single_star_does_not_cross_slash(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "sub").mkdir()
    (tmp_path / "src" / "foo.py").write_text("# foo\n")
    (tmp_path / "src" / "sub" / "deep.py").write_text("# deep\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "single star"],
        cwd=tmp_path, check=True, capture_output=True,
    )

    files = expand_patterns_to_files(("src/*.py",), tmp_path)

    assert files == ("src/foo.py",)


def test_expand_patterns_double_star_at_start_matches_root_files(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "root.py").write_text("# root\n")
    (tmp_path / "src" / "foo.py").write_text("# foo\n")
    (tmp_path / "deep").mkdir()
    (tmp_path / "deep" / "nested").mkdir()
    (tmp_path / "deep" / "nested" / "a.py").write_text("# a\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "double star"],
        cwd=tmp_path, check=True, capture_output=True,
    )

    files = expand_patterns_to_files(("**/*.py",), tmp_path)

    assert files == ("deep/nested/a.py", "root.py", "src/foo.py")


def test_expand_patterns_midpath_double_star_matches_zero_or_more_segments(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "sub").mkdir()
    (tmp_path / "src" / "foo.py").write_text("# foo\n")
    (tmp_path / "src" / "sub" / "deep.py").write_text("# deep\n")
    (tmp_path / "other.py").write_text("# other\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "midpath"],
        cwd=tmp_path, check=True, capture_output=True,
    )

    files = expand_patterns_to_files(("src/**/*.py",), tmp_path)

    assert files == ("src/foo.py", "src/sub/deep.py")


def test_resolve_targets_falls_back_to_random(tmp_path: Path) -> None:
    _repo_with_files(tmp_path)

    targets = resolve_targets(
        extensions=None,
        globs=None,
        targets_path=None,
        paths=None,
        repo_root=tmp_path,
    )

    assert len(targets) == 1
    assert targets[0].description == "random files"
    assert len(targets[0].files) > 0


# ---------------------------------------------------------------------------
# Property-based: JSONL roundtrip
# ---------------------------------------------------------------------------

def test_target_jsonl_roundtrip_property(tmp_path: Path) -> None:
    rng = random.Random(42)
    jsonl = tmp_path / "roundtrip.jsonl"

    generated: list[Target] = []
    lines: list[str] = []

    for _ in range(rng.randint(5, 20)):
        description = f"target-{uuid.uuid4()}"
        file_count = rng.randint(1, 5)
        files = tuple(f"src/{uuid.uuid4()}.py" for _ in range(file_count))
        scoping = f"scope-{uuid.uuid4()}" if rng.choice([True, False]) else None
        model_override = f"model-{uuid.uuid4()}" if rng.choice([True, False]) else None
        effort_override = rng.choice(["low", "medium", "high", None])

        target = Target(
            description=description,
            files=files,
            scoping=scoping,
            model_override=model_override,
            effort_override=effort_override,
        )
        generated.append(target)

        row: dict = {
            "description": description,
            "files": list(files),
        }
        if scoping is not None:
            row["scoping"] = scoping
        if model_override is not None:
            row["model-override"] = model_override
        if effort_override is not None:
            row["effort-override"] = effort_override
        lines.append(json.dumps(row))

    jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")

    loaded = load_targets_jsonl(jsonl)

    assert loaded == generated


# ---------------------------------------------------------------------------
# Hyphenated key mapping
# ---------------------------------------------------------------------------

def test_target_jsonl_hyphenated_keys(tmp_path: Path) -> None:
    jsonl = tmp_path / "hyphen.jsonl"
    data = {
        "description": "hyphen test",
        "files": ["*.py"],
        "effort-override": "max",
        "model-override": "claude-opus-4-20250514",
    }
    jsonl.write_text(json.dumps(data) + "\n", encoding="utf-8")

    targets = load_targets_jsonl(jsonl)

    assert len(targets) == 1
    assert targets[0].effort_override == "max"
    assert targets[0].model_override == "claude-opus-4-20250514"
