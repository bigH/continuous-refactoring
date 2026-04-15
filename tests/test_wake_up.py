from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from continuous_refactoring.migrations import (
    MigrationManifest,
    PhaseSpec,
    bump_last_touch,
    eligible_now,
    parse_iso,
)

NOW = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)

_PHASE = PhaseSpec(name="setup", file="phase-0-setup.md", done=False, ready_when="always")


def _ago(**delta: float) -> datetime:
    return NOW - timedelta(**delta)


def _future(**delta: float) -> datetime:
    return NOW + timedelta(**delta)


def _manifest(
    *,
    last_touch: datetime = NOW,
    wake_up_on: datetime | None = None,
) -> MigrationManifest:
    return MigrationManifest(
        name="test-migration",
        created_at="2026-04-01T00:00:00.000+00:00",
        last_touch=last_touch.isoformat(timespec="milliseconds"),
        wake_up_on=wake_up_on.isoformat(timespec="milliseconds") if wake_up_on else None,
        awaiting_human_review=False,
        status="ready",
        current_phase=0,
        phases=(_PHASE,),
    )


@pytest.mark.parametrize(
    ("last_touch", "wake_up_on", "is_eligible"),
    [
        (_ago(hours=5, minutes=59), None, False),
        (_ago(hours=5, minutes=59), _ago(days=30), False),
        (_ago(hours=1), _ago(days=365), False),
        (_ago(hours=5, minutes=59, seconds=59), None, False),
        (_ago(hours=6), _ago(hours=1), True),
        (_ago(hours=6), NOW, True),
        (_ago(hours=7), _future(hours=1), False),
        (_ago(days=7), None, True),
        (_ago(days=7), _future(days=1), True),
        (_ago(hours=6), None, True),
    ],
    ids=[
        "ineligible_under_cooldown",
        "ineligible_under_cooldown_even_with_past_wake",
        "ineligible_under_cooldown_with_far_past_wake",
        "ineligible_just_under_cooldown",
        "eligible_when_cooldown_over_and_wake_elapsed",
        "eligible_when_cooldown_over_and_wake_now",
        "ineligible_future_wake_within_stale_window",
        "eligible_stale_7d_with_no_wake",
        "eligible_stale_7d_with_future_wake",
        "eligible_no_wake_on_after_cooldown",
    ],
)
def test_eligible_now(
    last_touch: datetime, wake_up_on: datetime | None, is_eligible: bool
) -> None:
    manifest = _manifest(last_touch=last_touch, wake_up_on=wake_up_on)
    assert eligible_now(manifest, NOW) is is_eligible


# ---------------------------------------------------------------------------
# bump_last_touch
# ---------------------------------------------------------------------------

def test_bump_last_touch_returns_new_manifest() -> None:
    original = _manifest(last_touch=NOW - timedelta(hours=10))
    bumped = bump_last_touch(original, NOW)
    assert bumped is not original
    assert bumped.last_touch == NOW.isoformat(timespec="milliseconds")
    assert original.last_touch != bumped.last_touch


def test_bump_last_touch_preserves_other_fields() -> None:
    original = _manifest(
        last_touch=NOW - timedelta(hours=10),
        wake_up_on=NOW + timedelta(days=1),
    )
    bumped = bump_last_touch(original, NOW)
    assert bumped.name == original.name
    assert bumped.wake_up_on == original.wake_up_on
    assert bumped.phases == original.phases
    assert bumped.status == original.status


# ---------------------------------------------------------------------------
# parse_iso
# ---------------------------------------------------------------------------

def test_parse_iso_roundtrip() -> None:
    ts = NOW.isoformat(timespec="milliseconds")
    assert parse_iso(ts) == NOW
