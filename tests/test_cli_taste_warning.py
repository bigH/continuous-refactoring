from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

import continuous_refactoring.cli as cli
from conftest import init_repo
from continuous_refactoring.config import (
    DEFAULT_REPO_TASTE_PATH,
    default_taste_text,
    register_project,
    set_repo_taste_path,
)

_LEGACY_TASTE = "- Old taste without version header.\n"


def _write_global_taste(xdg_root: Path, text: str) -> None:
    taste_dir = xdg_root / "continuous-refactoring" / "global"
    taste_dir.mkdir(parents=True, exist_ok=True)
    (taste_dir / "taste.md").write_text(text, encoding="utf-8")


def _write_stale_taste(xdg_root: Path) -> None:
    _write_global_taste(xdg_root, _LEGACY_TASTE)


def _write_current_taste(xdg_root: Path) -> None:
    _write_global_taste(xdg_root, default_taste_text())


def _register_repo_with_taste(
    *,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    taste_text: str,
) -> None:
    init_repo(repo)
    monkeypatch.chdir(repo)

    project = register_project(repo)
    set_repo_taste_path(project.entry.uuid, DEFAULT_REPO_TASTE_PATH)
    taste_path = repo / DEFAULT_REPO_TASTE_PATH
    taste_path.parent.mkdir(parents=True, exist_ok=True)
    taste_path.write_text(taste_text, encoding="utf-8")


_SUBCOMMANDS: list[tuple[list[str], str]] = [
    (["cr", "init"], "_handle_init"),
    (["cr", "taste", "--global"], "_handle_taste"),
    (["cr", "upgrade"], "_handle_upgrade"),
    (["cr", "review", "list"], "handle_review"),
    (
        [
            "cr", "run-once",
            "--with", "codex", "--model", "m",
            "--scope-instruction", "s",
        ],
        "_handle_run_once",
    ),
    (
        [
            "cr", "run",
            "--with", "codex", "--model", "m",
            "--scope-instruction", "s", "--max-refactors", "1",
        ],
        "_handle_run",
    ),
]


def _run_cli_for_subcommand(
    *,
    xdg_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    handler_name: str,
    write_taste: Callable[[Path], None],
) -> None:
    write_taste(xdg_root)
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(cli, handler_name, lambda _: None)
    cli.cli_main()


@pytest.fixture
def xdg_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg))
    return xdg


# ---------------------------------------------------------------------------
# Warning fires for every subcommand with stale taste
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv,handler_name",
    _SUBCOMMANDS,
    ids=["init", "taste", "upgrade", "review", "run-once", "run"],
)
@pytest.mark.parametrize(
    "taste_writer,warns",
    [(_write_stale_taste, True), (_write_current_taste, False)],
    ids=["stale", "current"],
)
def test_taste_warning_behavior(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    xdg_root: Path,
    argv: list[str],
    handler_name: str,
    taste_writer: Callable[[Path], None],
    warns: bool,
) -> None:
    _run_cli_for_subcommand(
        xdg_root=xdg_root,
        monkeypatch=monkeypatch,
        argv=argv,
        handler_name=handler_name,
        write_taste=taste_writer,
    )

    err = capsys.readouterr().err
    if warns:
        assert err.count(cli._TASTE_WARNING) == 1
    else:
        assert cli._TASTE_WARNING not in err


def test_taste_warning_uses_configured_repo_taste(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    xdg_root: Path,
) -> None:
    _write_current_taste(xdg_root)
    repo = tmp_path / "repo"
    _register_repo_with_taste(
        repo=repo,
        monkeypatch=monkeypatch,
        taste_text=_LEGACY_TASTE,
    )

    monkeypatch.setattr(sys, "argv", ["cr", "upgrade"])
    monkeypatch.setattr(cli, "_handle_upgrade", lambda _: None)
    cli.cli_main()

    err = capsys.readouterr().err
    assert err.count(cli._TASTE_WARNING) == 1


def test_current_repo_taste_suppresses_stale_global_warning(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    xdg_root: Path,
) -> None:
    _write_stale_taste(xdg_root)
    repo = tmp_path / "repo"
    _register_repo_with_taste(
        repo=repo,
        monkeypatch=monkeypatch,
        taste_text=default_taste_text(),
    )

    monkeypatch.setattr(sys, "argv", ["cr", "upgrade"])
    monkeypatch.setattr(cli, "_handle_upgrade", lambda _: None)
    cli.cli_main()

    err = capsys.readouterr().err
    assert cli._TASTE_WARNING not in err


# ---------------------------------------------------------------------------
# Warning does not change exit codes
# ---------------------------------------------------------------------------


def test_warning_preserves_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    xdg_root: Path,
) -> None:
    _write_stale_taste(xdg_root)
    monkeypatch.setattr(sys, "argv", ["cr", "upgrade"])

    def fake_upgrade(_: object) -> None:
        raise SystemExit(42)

    monkeypatch.setattr(cli, "_handle_upgrade", fake_upgrade)

    with pytest.raises(SystemExit) as exc_info:
        cli.cli_main()

    assert exc_info.value.code == 42
    err = capsys.readouterr().err
    assert cli._TASTE_WARNING in err


# ---------------------------------------------------------------------------
# Warning does not mutate state
# ---------------------------------------------------------------------------


def test_warning_does_not_mutate_taste(
    monkeypatch: pytest.MonkeyPatch,
    xdg_root: Path,
) -> None:
    _write_stale_taste(xdg_root)

    taste_path = xdg_root / "continuous-refactoring" / "global" / "taste.md"
    before = taste_path.read_text(encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["cr", "upgrade"])
    monkeypatch.setattr(cli, "_handle_upgrade", lambda _: None)

    cli.cli_main()

    assert taste_path.read_text(encoding="utf-8") == before


def test_warning_skips_unreadable_taste(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    xdg_root: Path,
) -> None:
    _write_current_taste(xdg_root)
    taste_path = xdg_root / "continuous-refactoring" / "global" / "taste.md"
    io_error = OSError("mock read error")
    original_read_text = Path.read_text

    def broken_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == taste_path:
            raise io_error
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", broken_read_text)
    monkeypatch.setattr(sys, "argv", ["cr", "upgrade"])
    monkeypatch.setattr(cli, "_handle_upgrade", lambda _: None)

    cli.cli_main()

    err = capsys.readouterr().err
    assert cli._TASTE_WARNING not in err


def test_upgrade_exits_cleanly_on_malformed_manifest(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    xdg_root: Path,
) -> None:
    manifest = xdg_root / "continuous-refactoring" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("{", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["cr", "upgrade"])

    with pytest.raises(SystemExit) as exc_info:
        cli.cli_main()

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "Manifest file is malformed" in err


def test_upgrade_exits_cleanly_on_unreadable_global_taste(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    xdg_root: Path,
) -> None:
    _write_current_taste(xdg_root)
    manifest = xdg_root / "continuous-refactoring" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text('{"version": 1, "projects": {}}', encoding="utf-8")
    taste_path = xdg_root / "continuous-refactoring" / "global" / "taste.md"
    original_read_text = Path.read_text

    def broken_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == taste_path:
            raise OSError("mock read error")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", broken_read_text)
    monkeypatch.setattr(sys, "argv", ["cr", "upgrade"])

    with pytest.raises(SystemExit) as exc_info:
        cli.cli_main()

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "mock read error" in err
