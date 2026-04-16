from __future__ import annotations

import pytest

from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.scope_expansion import parse_scope_selection


def test_selection_parser_accepts_valid_output() -> None:
    selection = parse_scope_selection(
        "analysis\nselected-candidate: local-cluster — paired test and helper\n",
        ("seed", "local-cluster", "cross-cluster"),
    )

    assert selection.kind == "local-cluster"
    assert selection.reason == "paired test and helper"


def test_selection_parser_rejects_malformed_output() -> None:
    with pytest.raises(ContinuousRefactorError, match="unrecognised output"):
        parse_scope_selection(
            "pick local cluster\n",
            ("seed", "local-cluster", "cross-cluster"),
        )
