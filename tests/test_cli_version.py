from __future__ import annotations

import sys

import pytest

from continuous_refactoring import cli


def test_build_parser_uses_installed_package_metadata_for_version_banner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_names: list[str] = []

    def fake_metadata_version(package_name: str) -> str:
        package_names.append(package_name)
        return "9.8.7"

    monkeypatch.setattr(cli, "metadata_version", fake_metadata_version)

    cli.build_parser()

    assert package_names == [cli._PACKAGE_DISTRIBUTION]


def test_cli_main_version_prints_banner_without_stale_taste_warning(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "metadata_version", lambda _: "9.8.7")
    monkeypatch.setattr(sys, "argv", ["continuous-refactoring", "--version"])

    with pytest.raises(SystemExit) as exc_info:
        cli.cli_main()

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert captured.out == "continuous-refactoring 9.8.7\n"
    assert captured.err == ""
