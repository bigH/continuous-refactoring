from __future__ import annotations

import runpy


def test_main_module_invokes_cli_main(monkeypatch: object) -> None:
    seen: list[str] = []

    def fake_cli_main() -> None:
        seen.append("called")

    monkeypatch.setattr("continuous_refactoring.cli.cli_main", fake_cli_main)
    runpy.run_module("continuous_refactoring", run_name="__main__")
    assert seen == ["called"]
