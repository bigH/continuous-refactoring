from __future__ import annotations

import pytest

from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.effort import (
    EFFORT_TIERS,
    cap_effort,
    effort_exceeds,
    resolve_effort_budget,
    resolve_phase_effort,
    resolve_requested_effort,
    resolve_target_effort_budget,
)


def test_effort_tiers_are_ordered() -> None:
    assert EFFORT_TIERS == ("low", "medium", "high", "xhigh")
    assert effort_exceeds("xhigh", "high") is True
    assert effort_exceeds("medium", "high") is False
    assert cap_effort("xhigh", "medium") == "medium"
    assert cap_effort("low", "high") == "low"


def test_budget_uses_open_defaults_when_omitted() -> None:
    budget = resolve_effort_budget(None, None)

    assert budget.default_effort == "low"
    assert budget.max_allowed_effort == "xhigh"


def test_budget_defaults_missing_max_to_xhigh() -> None:
    budget = resolve_effort_budget("high", None)

    assert budget.default_effort == "high"
    assert budget.max_allowed_effort == "xhigh"


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


def test_target_effort_budget_uses_run_default_without_override() -> None:
    budget = resolve_effort_budget("medium", "xhigh")

    target_budget, resolution = resolve_target_effort_budget(budget, None)

    assert target_budget.default_effort == "medium"
    assert target_budget.max_allowed_effort == "xhigh"
    assert resolution.source == "default"
    assert resolution.requested_effort == "medium"
    assert resolution.effective_effort == "medium"
    assert resolution.reason == "run default effort"


def test_target_effort_budget_caps_override_and_updates_default() -> None:
    budget = resolve_effort_budget("low", "medium")

    target_budget, resolution = resolve_target_effort_budget(budget, "xhigh")

    assert target_budget.default_effort == "medium"
    assert target_budget.max_allowed_effort == "medium"
    assert resolution.source == "target-override"
    assert resolution.requested_effort == "xhigh"
    assert resolution.effective_effort == "medium"
    assert resolution.capped is True
    assert resolution.reason == "target effort override capped by run budget"


def test_phase_effort_uses_default_when_no_requirement() -> None:
    budget = resolve_effort_budget("medium", "xhigh")

    resolution = resolve_phase_effort(budget, None)

    assert resolution.source == "default"
    assert resolution.requested_effort == "medium"
    assert resolution.effective_effort == "medium"
    assert resolution.capped is False
    assert resolution.reason == "default effort"


def test_phase_effort_does_not_drop_below_default() -> None:
    budget = resolve_effort_budget("high", "xhigh")

    resolution = resolve_phase_effort(budget, "medium")

    assert resolution.source == "phase-required"
    assert resolution.requested_effort == "high"
    assert resolution.effective_effort == "high"
    assert resolution.capped is False
    assert resolution.reason == "phase required effort"


def test_phase_effort_promotes_then_caps_to_max() -> None:
    budget = resolve_effort_budget("medium", "high")

    resolution = resolve_phase_effort(
        budget,
        "xhigh",
        reason="migration phase override",
    )

    assert resolution.source == "phase-required"
    assert resolution.requested_effort == "xhigh"
    assert resolution.effective_effort == "high"
    assert resolution.max_allowed_effort == "high"
    assert resolution.capped is True
    assert resolution.reason == "migration phase override"


def test_resolution_event_fields_match_resolution() -> None:
    budget = resolve_effort_budget("low", "medium")
    resolution = resolve_requested_effort(
        budget,
        "xhigh",
        source="target-override",
        reason="test override",
    )

    assert resolution.event_fields() == {
        "effort_source": "target-override",
        "requested_effort": "xhigh",
        "effective_effort": "medium",
        "max_allowed_effort": "medium",
        "effort_capped": True,
        "effort_reason": "test override",
    }
