from __future__ import annotations

import continuous_refactoring.__main__ as cr_main


def test_main_invokes_cli_main(monkeypatch: object) -> None:
    seen: list[str] = []

    def fake_cli_main() -> None:
        seen.append("called")

    monkeypatch.setattr("continuous_refactoring.cli.cli_main", fake_cli_main)
    cr_main.main()
    assert seen == ["called"]
