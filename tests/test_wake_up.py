from __future__ import annotations

from datetime import datetime, timedelta, timezone

from continuous_refactoring.migrations import (
    MigrationManifest,
    PhaseSpec,
    bump_last_touch,
    eligible_now,
    parse_iso,
)

NOW = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)

_PHASE = PhaseSpec(name="setup", file="phase-0-setup.md", done=False, ready_when="always")


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


# ---------------------------------------------------------------------------
# Safety invariant: < 6h since last_touch → always ineligible
# ---------------------------------------------------------------------------

def test_fresh_migration_ineligible() -> None:
    m = _manifest(last_touch=NOW - timedelta(hours=5, minutes=59))
    assert not eligible_now(m, NOW)


def test_fresh_migration_ineligible_even_with_wake_up_in_past() -> None:
    m = _manifest(
        last_touch=NOW - timedelta(hours=5, minutes=59),
        wake_up_on=NOW - timedelta(days=30),
    )
    assert not eligible_now(m, NOW)


def test_adversarial_far_past_wake_up_blocked_by_cooldown() -> None:
    m = _manifest(
        last_touch=NOW - timedelta(hours=1),
        wake_up_on=NOW - timedelta(days=365),
    )
    assert not eligible_now(m, NOW)


def test_just_under_6h_ineligible() -> None:
    m = _manifest(last_touch=NOW - timedelta(hours=6) + timedelta(seconds=1))
    assert not eligible_now(m, NOW)


# ---------------------------------------------------------------------------
# Eligible: wake_up_on elapsed AND ≥ 6h
# ---------------------------------------------------------------------------

def test_eligible_wake_up_elapsed_and_6h() -> None:
    m = _manifest(
        last_touch=NOW - timedelta(hours=6),
        wake_up_on=NOW - timedelta(hours=1),
    )
    assert eligible_now(m, NOW)


def test_eligible_wake_up_exactly_now() -> None:
    m = _manifest(
        last_touch=NOW - timedelta(hours=6),
        wake_up_on=NOW,
    )
    assert eligible_now(m, NOW)


def test_ineligible_wake_up_in_future_and_under_7d() -> None:
    m = _manifest(
        last_touch=NOW - timedelta(hours=7),
        wake_up_on=NOW + timedelta(hours=1),
    )
    assert not eligible_now(m, NOW)


# ---------------------------------------------------------------------------
# Eligible: 7d stale (no wake_up_on or future wake_up_on overridden)
# ---------------------------------------------------------------------------

def test_eligible_7d_stale_no_wake_up() -> None:
    m = _manifest(last_touch=NOW - timedelta(days=7))
    assert eligible_now(m, NOW)


def test_eligible_7d_stale_overrides_future_wake_up() -> None:
    m = _manifest(
        last_touch=NOW - timedelta(days=7),
        wake_up_on=NOW + timedelta(days=1),
    )
    assert eligible_now(m, NOW)


# ---------------------------------------------------------------------------
# Eligible: no wake_up_on and ≥ 6h
# ---------------------------------------------------------------------------

def test_eligible_no_wake_up_and_6h() -> None:
    m = _manifest(last_touch=NOW - timedelta(hours=6))
    assert eligible_now(m, NOW)


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
