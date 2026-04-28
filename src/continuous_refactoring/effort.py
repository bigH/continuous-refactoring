from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Literal, cast

from continuous_refactoring.artifacts import ContinuousRefactorError

__all__ = [
    "DEFAULT_EFFORT",
    "DEFAULT_MAX_ALLOWED_EFFORT",
    "EFFORT_TIERS",
    "EffortBudget",
    "EffortResolution",
    "EffortTier",
    "cap_effort",
    "effort_exceeds",
    "max_effort",
    "parse_effort_arg",
    "require_effort_tier",
    "resolve_effort_budget",
    "resolve_phase_effort",
    "resolve_requested_effort",
]

EffortTier = Literal["low", "medium", "high", "xhigh"]
EFFORT_TIERS: tuple[EffortTier, ...] = ("low", "medium", "high", "xhigh")
DEFAULT_EFFORT: EffortTier = "low"
DEFAULT_MAX_ALLOWED_EFFORT: EffortTier = "xhigh"
_EFFORT_RANK = {tier: index for index, tier in enumerate(EFFORT_TIERS)}


@dataclass(frozen=True)
class EffortBudget:
    default_effort: EffortTier
    max_allowed_effort: EffortTier


@dataclass(frozen=True)
class EffortResolution:
    source: str
    requested_effort: EffortTier
    effective_effort: EffortTier
    max_allowed_effort: EffortTier
    capped: bool
    reason: str

    def event_fields(self) -> dict[str, object]:
        return {
            "effort_source": self.source,
            "requested_effort": self.requested_effort,
            "effective_effort": self.effective_effort,
            "max_allowed_effort": self.max_allowed_effort,
            "effort_capped": self.capped,
            "effort_reason": self.reason,
        }


def require_effort_tier(value: object, *, field: str) -> EffortTier:
    if not isinstance(value, str):
        raise ContinuousRefactorError(f"{field} must be an effort tier string")
    if value not in _EFFORT_RANK:
        allowed = ", ".join(EFFORT_TIERS)
        raise ContinuousRefactorError(
            f"{field} must be one of: {allowed}; got {value!r}"
        )
    return cast(EffortTier, value)


def parse_effort_arg(value: str) -> EffortTier:
    try:
        return require_effort_tier(value, field="effort")
    except ContinuousRefactorError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def effort_exceeds(left: EffortTier, right: EffortTier) -> bool:
    return _EFFORT_RANK[left] > _EFFORT_RANK[right]


def max_effort(left: EffortTier, right: EffortTier) -> EffortTier:
    if effort_exceeds(left, right):
        return left
    return right


def cap_effort(requested: EffortTier, max_allowed: EffortTier) -> EffortTier:
    if effort_exceeds(requested, max_allowed):
        return max_allowed
    return requested


def resolve_effort_budget(
    default_effort: object | None,
    max_allowed_effort: object | None,
) -> EffortBudget:
    default = (
        DEFAULT_EFFORT
        if default_effort is None
        else require_effort_tier(default_effort, field="default_effort")
    )
    maximum = (
        DEFAULT_MAX_ALLOWED_EFFORT
        if max_allowed_effort is None
        else require_effort_tier(max_allowed_effort, field="max_allowed_effort")
    )
    if effort_exceeds(default, maximum):
        raise ContinuousRefactorError(
            "--max-allowed-effort must be greater than or equal to --default-effort"
        )
    return EffortBudget(default_effort=default, max_allowed_effort=maximum)


def resolve_requested_effort(
    budget: EffortBudget,
    requested_effort: object | None,
    *,
    source: str,
    reason: str,
) -> EffortResolution:
    requested = (
        budget.default_effort
        if requested_effort is None
        else require_effort_tier(requested_effort, field=f"{source} effort")
    )
    effective = cap_effort(requested, budget.max_allowed_effort)
    return EffortResolution(
        source=source,
        requested_effort=requested,
        effective_effort=effective,
        max_allowed_effort=budget.max_allowed_effort,
        capped=effective != requested,
        reason=reason,
    )


def resolve_phase_effort(
    budget: EffortBudget,
    required_effort: EffortTier | None,
    *,
    reason: str | None = None,
) -> EffortResolution:
    requested = (
        budget.default_effort
        if required_effort is None
        else max_effort(budget.default_effort, required_effort)
    )
    source = "phase-required" if required_effort is not None else "default"
    effective = cap_effort(requested, budget.max_allowed_effort)
    return EffortResolution(
        source=source,
        requested_effort=requested,
        effective_effort=effective,
        max_allowed_effort=budget.max_allowed_effort,
        capped=effective != requested,
        reason=reason or (
            "phase required effort" if required_effort is not None else "default effort"
        ),
    )
