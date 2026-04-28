from __future__ import annotations

import pytest

from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.effort import (
    EFFORT_TIERS,
    cap_effort,
    effort_exceeds,
    resolve_effort_budget,
    resolve_requested_effort,
)


def test_effort_tiers_are_ordered() -> None:
    assert EFFORT_TIERS == ("low", "medium", "high", "xhigh")
    assert effort_exceeds("xhigh", "high") is True
    assert effort_exceeds("medium", "high") is False
    assert cap_effort("xhigh", "medium") == "medium"
    assert cap_effort("low", "high") == "low"


def test_budget_defaults_max_to_default_effort() -> None:
    budget = resolve_effort_budget("high", None)

    assert budget.default_effort == "high"
    assert budget.max_allowed_effort == "high"


def test_budget_rejects_max_below_default() -> None:
    with pytest.raises(ContinuousRefactorError, match="max-allowed-effort"):
        resolve_effort_budget("high", "medium")


def test_target_override_requests_default_then_caps_to_max() -> None:
    budget = resolve_effort_budget("low", "medium")
    resolution = resolve_requested_effort(
        budget,
        "xhigh",
        source="target-override",
        reason="test override",
    )

    assert resolution.requested_effort == "xhigh"
    assert resolution.effective_effort == "medium"
    assert resolution.max_allowed_effort == "medium"
    assert resolution.capped is True
