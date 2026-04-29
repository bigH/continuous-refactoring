from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest

from conftest import init_repo, init_repo_with_temp_home, load_single_registered_project

from continuous_refactoring.cli import _handle_init, _handle_taste, build_parser
from continuous_refactoring.config import (
    DEFAULT_REPO_TASTE_PATH,
    app_data_dir,
    default_taste_text,
    resolve_live_migrations_dir,
    resolve_project_taste_path,
    register_project,
)


# ---------------------------------------------------------------------------
# init subcommand
# ---------------------------------------------------------------------------


def make_init_args(
    path: Path,
    *,
    in_repo_taste: Path | None = None,
    live_migrations_dir: Path | None = None,
    force: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        path=path,
        in_repo_taste=in_repo_taste,
        live_migrations_dir=live_migrations_dir,
        force=force,
    )


def test_init_creates_manifest_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)

    args = argparse.Namespace(path=repo)
    _handle_init(args)

    project = load_single_registered_project()
    assert project.entry.path == str(repo.resolve())


def test_init_creates_project_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)

    args = argparse.Namespace(path=repo)
    _handle_init(args)

    project = load_single_registered_project()
    assert project.project_dir.is_dir()


def test_init_creates_taste_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)

    args = argparse.Namespace(path=repo)
    _handle_init(args)

    project = load_single_registered_project()
    assert project.taste_path.exists()
    assert project.taste_path.read_text(encoding="utf-8") == default_taste_text()


def test_init_in_repo_taste_default_creates_and_stores(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)

    args = argparse.Namespace(
        path=repo,
        in_repo_taste=Path(DEFAULT_REPO_TASTE_PATH),
        live_migrations_dir=None,
    )
    _handle_init(args)

    project = load_single_registered_project()
    taste_path = (repo / DEFAULT_REPO_TASTE_PATH).resolve()
    assert project.entry.repo_taste_path == DEFAULT_REPO_TASTE_PATH
    assert taste_path.exists()
    assert taste_path.read_text(encoding="utf-8") == default_taste_text()
    assert not project.taste_path.exists()
    assert resolve_project_taste_path(project) == taste_path

    out = capsys.readouterr().out
    assert f"Taste file: {taste_path}" in out


def test_init_in_repo_taste_custom_creates_and_stores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)

    args = argparse.Namespace(
        path=repo,
        in_repo_taste=Path("config/refactor-taste.md"),
        live_migrations_dir=None,
    )
    _handle_init(args)

    project = load_single_registered_project()
    taste_path = repo / "config" / "refactor-taste.md"
    assert project.entry.repo_taste_path == "config/refactor-taste.md"
    assert taste_path.exists()
    assert taste_path.read_text(encoding="utf-8") == default_taste_text()


def test_init_in_repo_taste_preserves_existing_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    taste_path = repo / DEFAULT_REPO_TASTE_PATH
    taste_path.parent.mkdir(parents=True, exist_ok=True)
    taste_path.write_text("- Existing repo taste.\n", encoding="utf-8")

    _handle_init(
        argparse.Namespace(
            path=repo,
            in_repo_taste=Path(DEFAULT_REPO_TASTE_PATH),
            live_migrations_dir=None,
        )
    )

    assert taste_path.read_text(encoding="utf-8") == "- Existing repo taste.\n"


def test_init_without_in_repo_taste_preserves_existing_choice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    custom_content = "- Existing repo taste.\n"
    _handle_init(
        argparse.Namespace(
            path=repo,
            in_repo_taste=Path(DEFAULT_REPO_TASTE_PATH),
            live_migrations_dir=None,
        )
    )
    (repo / DEFAULT_REPO_TASTE_PATH).write_text(custom_content, encoding="utf-8")

    _handle_init(argparse.Namespace(path=repo))

    project = load_single_registered_project()
    assert project.entry.repo_taste_path == DEFAULT_REPO_TASTE_PATH
    assert resolve_project_taste_path(project) == (
        repo / DEFAULT_REPO_TASTE_PATH
    ).resolve()
    assert (
        (repo / DEFAULT_REPO_TASTE_PATH).read_text(encoding="utf-8")
        == custom_content
    )


def test_init_in_repo_taste_reinitializes_choice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    _handle_init(
        argparse.Namespace(
            path=repo,
            in_repo_taste=Path(DEFAULT_REPO_TASTE_PATH),
            live_migrations_dir=None,
        )
    )

    _handle_init(
        argparse.Namespace(
            path=repo,
            in_repo_taste=Path("taste/refactoring.md"),
            live_migrations_dir=None,
        )
    )

    project = load_single_registered_project()
    assert project.entry.repo_taste_path == "taste/refactoring.md"
    assert (repo / "taste" / "refactoring.md").exists()


def test_init_in_repo_taste_moves_existing_xdg_taste_and_keeps_uuid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    _handle_init(make_init_args(repo))
    first = load_single_registered_project()
    first.taste_path.write_text("- Edited XDG taste.\n", encoding="utf-8")

    _handle_init(make_init_args(repo, in_repo_taste=Path("config/taste.md")))

    project = load_single_registered_project()
    destination = (repo / "config" / "taste.md").resolve()
    assert project.entry.uuid == first.entry.uuid
    assert project.entry.repo_taste_path == "config/taste.md"
    assert resolve_project_taste_path(project) == destination
    assert destination.read_text(encoding="utf-8") == "- Edited XDG taste.\n"
    assert not first.taste_path.exists()


def test_init_in_repo_taste_path_change_moves_existing_repo_taste(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    _handle_init(make_init_args(repo, in_repo_taste=Path(DEFAULT_REPO_TASTE_PATH)))
    first = load_single_registered_project()
    old_path = repo / DEFAULT_REPO_TASTE_PATH
    old_path.write_text("- Edited repo taste.\n", encoding="utf-8")

    _handle_init(make_init_args(repo, in_repo_taste=Path("taste/refactoring.md")))

    project = load_single_registered_project()
    new_path = repo / "taste" / "refactoring.md"
    assert project.entry.uuid == first.entry.uuid
    assert project.entry.repo_taste_path == "taste/refactoring.md"
    assert new_path.read_text(encoding="utf-8") == "- Edited repo taste.\n"
    assert not old_path.exists()


def test_init_in_repo_taste_conflict_fails_without_force(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    _handle_init(make_init_args(repo))
    project = load_single_registered_project()
    source = project.taste_path
    destination = repo / "config" / "taste.md"
    source.write_text("- Source taste.\n", encoding="utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("- Existing destination taste.\n", encoding="utf-8")
    capsys.readouterr()

    with pytest.raises(SystemExit) as exc_info:
        _handle_init(make_init_args(repo, in_repo_taste=Path("config/taste.md")))

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "Taste destination already exists" in err
    assert "--force" in err
    unchanged = load_single_registered_project()
    assert unchanged.entry.uuid == project.entry.uuid
    assert unchanged.entry.repo_taste_path is None
    assert source.read_text(encoding="utf-8") == "- Source taste.\n"
    assert destination.read_text(encoding="utf-8") == "- Existing destination taste.\n"


def test_init_in_repo_taste_conflict_force_replaces_with_old_taste(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    _handle_init(make_init_args(repo))
    project = load_single_registered_project()
    source = project.taste_path
    destination = repo / "config" / "taste.md"
    source.write_text("- Source taste wins.\n", encoding="utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("- Destination loses.\n", encoding="utf-8")

    _handle_init(
        make_init_args(repo, in_repo_taste=Path("config/taste.md"), force=True)
    )

    updated = load_single_registered_project()
    assert updated.entry.uuid == project.entry.uuid
    assert updated.entry.repo_taste_path == "config/taste.md"
    assert destination.read_text(encoding="utf-8") == "- Source taste wins.\n"
    assert not source.exists()


def test_init_in_repo_taste_rejects_outside_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)

    args = argparse.Namespace(
        path=repo,
        in_repo_taste=Path("../taste.md"),
        live_migrations_dir=None,
    )
    with pytest.raises(SystemExit) as exc_info:
        _handle_init(args)

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "--in-repo-taste must be inside the repo" in err


@pytest.mark.parametrize(
    "taste_arg",
    [Path("."), Path("existing-dir")],
    ids=["repo-root", "existing-dir"],
)
def test_init_in_repo_taste_rejects_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    taste_arg: Path,
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    (repo / "existing-dir").mkdir()

    args = argparse.Namespace(
        path=repo,
        in_repo_taste=taste_arg,
        live_migrations_dir=None,
    )
    with pytest.raises(SystemExit) as exc_info:
        _handle_init(args)

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "--in-repo-taste must point to a file" in err


def test_init_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    args = argparse.Namespace(path=repo)

    _handle_init(args)
    first = load_single_registered_project()
    taste_path = first.taste_path
    custom_content = "- My custom taste.\n"
    taste_path.write_text(custom_content, encoding="utf-8")

    _handle_init(args)
    second = load_single_registered_project()
    assert first.entry.uuid == second.entry.uuid
    assert taste_path.read_text(encoding="utf-8") == custom_content


def test_init_with_explicit_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = init_repo_with_temp_home(
        tmp_path,
        monkeypatch,
        repo_name="explicit-project",
    )

    # cwd is NOT the repo -- explicit --path should win
    monkeypatch.chdir(tmp_path)
    args = argparse.Namespace(path=repo)
    _handle_init(args)

    project = load_single_registered_project()
    assert project.entry.path == str(repo.resolve())

    out = capsys.readouterr().out
    assert project.entry.uuid in out


def test_init_detects_git_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch, repo_name="with-remote")
    remote_url = "https://example.com/org/repo.git"
    subprocess.run(
        ["git", "remote", "add", "origin", remote_url],
        cwd=repo, check=True, capture_output=True,
    )

    args = argparse.Namespace(path=repo)
    _handle_init(args)

    assert (tmp_path / "xdg").is_dir()
    project = load_single_registered_project()
    assert project.entry.git_remote == remote_url


def test_init_subparser_accepts_in_repo_taste_optional_path() -> None:
    parser = build_parser()

    default_args = parser.parse_args(["init", "--in-repo-taste"])
    custom_args = parser.parse_args(["init", "--in-repo-taste", "config/taste.md"])
    force_args = parser.parse_args(["init", "--force"])

    assert default_args.in_repo_taste == Path(DEFAULT_REPO_TASTE_PATH)
    assert custom_args.in_repo_taste == Path("config/taste.md")
    assert force_args.force is True


def test_init_live_migrations_dir_creates_and_stores(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)

    args = argparse.Namespace(path=repo, live_migrations_dir=Path(".migrations"))
    _handle_init(args)

    project = load_single_registered_project()
    assert project.entry.live_migrations_dir == ".migrations"
    assert (repo / ".migrations").is_dir()

    out = capsys.readouterr().out
    assert project.entry.uuid in out
    assert "Live migrations dir:" in out

    # Second call is idempotent: overwrites value, no duplicate entries
    args2 = argparse.Namespace(path=repo, live_migrations_dir=Path("other-dir"))
    _handle_init(args2)

    project2 = load_single_registered_project()
    assert project2.entry.uuid == project.entry.uuid
    assert project2.entry.live_migrations_dir == "other-dir"
    assert (repo / "other-dir").is_dir()


def test_init_without_live_migrations_dir_preserves_existing_choice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    _handle_init(make_init_args(repo, live_migrations_dir=Path(".migrations")))
    live_file = repo / ".migrations" / "plan.md"
    live_file.write_text("phase 1\n", encoding="utf-8")

    _handle_init(make_init_args(repo))

    project = load_single_registered_project()
    assert project.entry.live_migrations_dir == ".migrations"
    assert resolve_live_migrations_dir(project) == (repo / ".migrations").resolve()
    assert live_file.read_text(encoding="utf-8") == "phase 1\n"


def test_init_live_migrations_dir_change_moves_existing_contents_and_keeps_uuid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    _handle_init(make_init_args(repo, live_migrations_dir=Path(".migrations")))
    first = load_single_registered_project()
    old_file = repo / ".migrations" / "feature" / "phase.md"
    old_file.parent.mkdir(parents=True, exist_ok=True)
    old_file.write_text("definition of done\n", encoding="utf-8")

    _handle_init(make_init_args(repo, live_migrations_dir=Path("migrations/live")))

    project = load_single_registered_project()
    new_dir = repo / "migrations" / "live"
    assert project.entry.uuid == first.entry.uuid
    assert project.entry.live_migrations_dir == "migrations/live"
    assert resolve_live_migrations_dir(project) == new_dir.resolve()
    assert (new_dir / "feature" / "phase.md").read_text(encoding="utf-8") == (
        "definition of done\n"
    )
    assert not (repo / ".migrations").exists()


def test_init_live_migrations_dir_conflict_fails_without_force(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    _handle_init(make_init_args(repo, live_migrations_dir=Path(".migrations")))
    project = load_single_registered_project()
    source_file = repo / ".migrations" / "source.md"
    destination_file = repo / "migrations" / "live" / "destination.md"
    source_file.write_text("source\n", encoding="utf-8")
    destination_file.parent.mkdir(parents=True, exist_ok=True)
    destination_file.write_text("destination\n", encoding="utf-8")
    capsys.readouterr()

    with pytest.raises(SystemExit) as exc_info:
        _handle_init(make_init_args(repo, live_migrations_dir=Path("migrations/live")))

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "Live migrations destination already exists and is not empty" in err
    assert "--force" in err
    unchanged = load_single_registered_project()
    assert unchanged.entry.uuid == project.entry.uuid
    assert unchanged.entry.live_migrations_dir == ".migrations"
    assert source_file.read_text(encoding="utf-8") == "source\n"
    assert destination_file.read_text(encoding="utf-8") == "destination\n"


def test_init_live_migrations_dir_conflict_force_replaces_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    _handle_init(make_init_args(repo, live_migrations_dir=Path(".migrations")))
    project = load_single_registered_project()
    source_file = repo / ".migrations" / "source.md"
    destination_dir = repo / "migrations" / "live"
    destination_file = destination_dir / "destination.md"
    source_file.write_text("source wins\n", encoding="utf-8")
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_file.write_text("destination loses\n", encoding="utf-8")

    _handle_init(
        make_init_args(
            repo,
            live_migrations_dir=Path("migrations/live"),
            force=True,
        )
    )

    updated = load_single_registered_project()
    assert updated.entry.uuid == project.entry.uuid
    assert updated.entry.live_migrations_dir == "migrations/live"
    assert (
        (destination_dir / "source.md").read_text(encoding="utf-8")
        == "source wins\n"
    )
    assert not destination_file.exists()
    assert not (repo / ".migrations").exists()


def test_init_live_migrations_dir_rejects_outside_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)

    args = argparse.Namespace(path=repo, live_migrations_dir=Path("../outside"))
    with pytest.raises(SystemExit) as exc_info:
        _handle_init(args)

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "must be inside the repo" in err


def test_init_exits_cleanly_on_malformed_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    manifest = app_data_dir() / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("{", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        _handle_init(argparse.Namespace(path=repo))

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "Manifest file is malformed" in err


# ---------------------------------------------------------------------------
# taste subcommand
# ---------------------------------------------------------------------------


def test_taste_prints_project_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    monkeypatch.chdir(repo)

    register_project(repo)

    args = argparse.Namespace(global_=False)
    _handle_taste(args)

    out = capsys.readouterr().out.strip()
    assert out.endswith("taste.md")
    assert Path(out).exists()


def test_taste_prints_configured_repo_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    _handle_init(
        argparse.Namespace(
            path=repo,
            in_repo_taste=Path(DEFAULT_REPO_TASTE_PATH),
            live_migrations_dir=None,
        )
    )
    monkeypatch.chdir(repo)
    capsys.readouterr()

    _handle_taste(argparse.Namespace(global_=False))

    out = capsys.readouterr().out.strip()
    expected = (repo / DEFAULT_REPO_TASTE_PATH).resolve()
    assert out == str(expected)
    assert expected.exists()


def test_taste_creates_file_if_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    monkeypatch.chdir(repo)

    project = register_project(repo)
    # Ensure it exists first, then remove it
    taste_path = project.project_dir / "taste.md"
    if taste_path.exists():
        taste_path.unlink()
    assert not taste_path.exists()

    args = argparse.Namespace(global_=False)
    _handle_taste(args)

    out = capsys.readouterr().out.strip()
    assert Path(out).exists()
    assert Path(out).read_text(encoding="utf-8") == default_taste_text()


def test_taste_global_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    init_repo_with_temp_home(tmp_path, monkeypatch, repo_name="project")

    args = argparse.Namespace(global_=True)
    _handle_taste(args)

    out = capsys.readouterr().out.strip()
    expected = app_data_dir() / "global" / "taste.md"
    assert out == str(expected)
    assert expected.exists()
    assert expected.read_text(encoding="utf-8") == default_taste_text()


def test_taste_errors_without_init(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "unregistered"
    init_repo(repo)
    monkeypatch.chdir(repo)

    args = argparse.Namespace(global_=False)
    with pytest.raises(SystemExit) as exc_info:
        _handle_taste(args)

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "not initialized" in err


def test_taste_exits_cleanly_on_manifest_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = init_repo_with_temp_home(tmp_path, monkeypatch)
    monkeypatch.chdir(repo)
    register_project(repo)
    manifest = app_data_dir() / "manifest.json"

    original_read_text = Path.read_text

    def patched_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == manifest:
            raise OSError("mock read error")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", patched_read_text)

    with pytest.raises(SystemExit) as exc_info:
        _handle_taste(argparse.Namespace(global_=False))

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "Manifest file could not be read" in err
