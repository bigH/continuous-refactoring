from __future__ import annotations

import sys
from pathlib import Path

import pytest

from continuous_refactoring.cli import cli_main
from continuous_refactoring.config import default_taste_text

_WARNING = (
    "warning: taste out of date — "
    "run `continuous-refactoring taste --upgrade`"
)

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


# ---------------------------------------------------------------------------
# Warning fires for every subcommand with stale taste
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv,handler",
    _SUBCOMMANDS,
    ids=["init", "taste", "upgrade", "run-once", "run"],
)
def test_stale_warning_fires(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    handler: str,
) -> None:
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg))
    _write_stale_taste(xdg)
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(f"continuous_refactoring.cli.{handler}", lambda _: None)

    cli_main()

    err = capsys.readouterr().err
    assert err.count(_WARNING) == 1


# ---------------------------------------------------------------------------
# No warning when taste is current
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv,handler",
    _SUBCOMMANDS,
    ids=["init", "taste", "upgrade", "run-once", "run"],
)
def test_no_warning_when_current(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    handler: str,
) -> None:
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg))
    _write_current_taste(xdg)
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(f"continuous_refactoring.cli.{handler}", lambda _: None)

    cli_main()

    err = capsys.readouterr().err
    assert _WARNING not in err


# ---------------------------------------------------------------------------
# Warning does not change exit codes
# ---------------------------------------------------------------------------


def test_warning_preserves_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg))
    _write_stale_taste(xdg)
    monkeypatch.setattr(sys, "argv", ["cr", "upgrade"])

    def fake_upgrade(_: object) -> None:
        raise SystemExit(42)

    monkeypatch.setattr("continuous_refactoring.cli._handle_upgrade", fake_upgrade)

    with pytest.raises(SystemExit) as exc_info:
        cli_main()

    assert exc_info.value.code == 42
    err = capsys.readouterr().err
    assert _WARNING in err


# ---------------------------------------------------------------------------
# Warning does not mutate state
# ---------------------------------------------------------------------------


def test_warning_does_not_mutate_taste(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg))
    _write_stale_taste(xdg)

    taste_path = xdg / "continuous-refactoring" / "global" / "taste.md"
    before = taste_path.read_text(encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["cr", "upgrade"])
    monkeypatch.setattr("continuous_refactoring.cli._handle_upgrade", lambda _: None)

    cli_main()

    assert taste_path.read_text(encoding="utf-8") == before
