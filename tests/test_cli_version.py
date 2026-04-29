from __future__ import annotations

import pytest

from continuous_refactoring import cli


def test_global_version_uses_installed_package_metadata(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    package_names: list[str] = []

    def fake_metadata_version(package_name: str) -> str:
        package_names.append(package_name)
        return "9.8.7"

    monkeypatch.setattr(cli, "metadata_version", fake_metadata_version)

    parser = cli.build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])

    assert exc_info.value.code == 0
    assert package_names == ["continuous-refactoring"]
    assert capsys.readouterr().out == "continuous-refactoring 9.8.7\n"
