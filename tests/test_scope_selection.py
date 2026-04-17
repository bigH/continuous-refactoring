from __future__ import annotations

import pytest

from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.scope_expansion import parse_scope_selection

_KINDS = ("seed", "local-cluster", "cross-cluster")


def test_selection_parser_accepts_valid_output() -> None:
    selection = parse_scope_selection(
        "analysis\nselected-candidate: local-cluster — paired test and helper\n",
        _KINDS,
    )

    assert selection.kind == "local-cluster"
    assert selection.reason == "paired test and helper"


def test_selection_parser_defaults_reason_to_kind_when_missing() -> None:
    selection = parse_scope_selection("selected-candidate: seed\n", _KINDS)

    assert selection.kind == "seed"
    assert selection.reason == "seed"


def test_selection_parser_rejects_malformed_output() -> None:
    with pytest.raises(ContinuousRefactorError, match="unrecognised output"):
        parse_scope_selection("pick local cluster\n", _KINDS)


def test_selection_parser_error_quotes_last_non_blank_line() -> None:
    with pytest.raises(ContinuousRefactorError, match=r"'second line'"):
        parse_scope_selection("first line\nsecond line\n", _KINDS)


def test_selection_parser_rejects_empty_output() -> None:
    with pytest.raises(ContinuousRefactorError, match="no output"):
        parse_scope_selection("   \n\n", _KINDS)


def test_selection_parser_rejects_kind_outside_available_candidates() -> None:
    with pytest.raises(ContinuousRefactorError, match="unavailable candidate"):
        parse_scope_selection(
            "selected-candidate: cross-cluster\n",
            ("seed", "local-cluster"),
        )
