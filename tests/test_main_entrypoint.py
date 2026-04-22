from __future__ import annotations

import runpy
import sys

import continuous_refactoring.__main__ as main_module


def test_main_module_invokes_cli_main(monkeypatch: object) -> None:
    seen: list[str] = []

    def fake_cli_main() -> None:
        seen.append("called")

    monkeypatch.setattr("continuous_refactoring.cli.cli_main", fake_cli_main)
    monkeypatch.delitem(sys.modules, "continuous_refactoring.__main__", raising=False)
    runpy.run_module("continuous_refactoring", run_name="__main__")
    assert seen == ["called"]


def test_main_module_has_no_public_api() -> None:
    assert main_module.__all__ == ()
    assert not hasattr(main_module, "cli_main")
