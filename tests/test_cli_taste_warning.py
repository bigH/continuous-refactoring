from __future__ import annotations

import sys
from pathlib import Path
from collections.abc import Callable

import pytest

from continuous_refactoring.cli import cli_main
from continuous_refactoring.cli import _TASTE_WARNING
from continuous_refactoring.config import default_taste_text

_LEGACY_TASTE = "- Old taste without version header.\n"


def _write_stale_taste(xdg_root: Path) -> None:
    taste_dir = xdg_root / "continuous-refactoring" / "global"
    taste_dir.mkdir(parents=True, exist_ok=True)
    (taste_dir / "taste.md").write_text(_LEGACY_TASTE, encoding="utf-8")


def _write_current_taste(xdg_root: Path) -> None:
    taste_dir = xdg_root / "continuous-refactoring" / "global"
    taste_dir.mkdir(parents=True, exist_ok=True)
    (taste_dir / "taste.md").write_text(default_taste_text(), encoding="utf-8")


_SUBCOMMANDS: list[tuple[list[str], str]] = [
    (["cr", "init"], "_handle_init"),
    (["cr", "taste", "--global"], "_handle_taste"),
    (["cr", "upgrade"], "_handle_upgrade"),
    (
        [
            "cr", "run-once",
            "--with", "codex", "--model", "m", "--effort", "e",
            "--scope-instruction", "s",
        ],
        "_handle_run_once",
    ),
    (
        [
            "cr", "run",
            "--with", "codex", "--model", "m", "--effort", "e",
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
    handler: str,
    write_taste: Callable[[Path], None],
) -> None:
    write_taste(xdg_root)
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(f"continuous_refactoring.cli.{handler}", lambda _: None)
    cli_main()


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
    "argv,handler",
    _SUBCOMMANDS,
    ids=["init", "taste", "upgrade", "run-once", "run"],
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
    handler: str,
    taste_writer: Callable[[Path], None],
    warns: bool,
) -> None:
    _run_cli_for_subcommand(
        xdg_root=xdg_root,
        monkeypatch=monkeypatch,
        argv=argv,
        handler=handler,
        write_taste=taste_writer,
    )

    err = capsys.readouterr().err
    if warns:
        assert err.count(_TASTE_WARNING) == 1
    else:
        assert _TASTE_WARNING not in err


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

    monkeypatch.setattr("continuous_refactoring.cli._handle_upgrade", fake_upgrade)

    with pytest.raises(SystemExit) as exc_info:
        cli_main()

    assert exc_info.value.code == 42
    err = capsys.readouterr().err
    assert _TASTE_WARNING in err


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
    monkeypatch.setattr("continuous_refactoring.cli._handle_upgrade", lambda _: None)

    cli_main()

    assert taste_path.read_text(encoding="utf-8") == before
