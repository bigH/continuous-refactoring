from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

import continuous_refactoring
import continuous_refactoring.loop
from continuous_refactoring.artifacts import CommandCapture
from continuous_refactoring.migrations import (
    MigrationManifest,
    PhaseSpec,
    eligible_now,
    load_manifest,
    migration_root,
    save_manifest,
)
from continuous_refactoring.phases import ExecutePhaseOutcome

from conftest import (
    init_repo,
    make_run_once_args,
    noop_agent,
    noop_tests,
)

_PHASE_0 = PhaseSpec(name="setup", file="phase-0-setup.md", done=False, ready_when="always")
_PHASE_1 = PhaseSpec(name="migrate", file="phase-1-migrate.md", done=False, ready_when="phase 0 done")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _git_commit_all(repo_root: Path) -> None:
    continuous_refactoring.run_command(["git", "add", "-A"], cwd=repo_root)
    continuous_refactoring.run_command(
        ["git", "commit", "-m", "add test fixtures"], cwd=repo_root,
    )


def _make_manifest(
    name: str,
    *,
    last_touch: datetime,
    wake_up_on: datetime | None = None,
    created_at: datetime | None = None,
) -> MigrationManifest:
    ts = (created_at or _utc_now()).isoformat(timespec="milliseconds")
    return MigrationManifest(
        name=name,
        created_at=ts,
        last_touch=last_touch.isoformat(timespec="milliseconds"),
        wake_up_on=wake_up_on.isoformat(timespec="milliseconds") if wake_up_on else None,
        awaiting_human_review=False,
        status="in-progress",
        current_phase=0,
        phases=(_PHASE_0, _PHASE_1),
    )


def _save(manifest: MigrationManifest, live_dir: Path) -> Path:
    root = migration_root(live_dir, manifest.name)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "manifest.json"
    save_manifest(manifest, path)
    return path


def _patch_live_dir(
    monkeypatch: pytest.MonkeyPatch, live_dir: Path,
) -> None:
    monkeypatch.setattr(
        "continuous_refactoring.loop._resolve_live_migrations_dir",
        lambda _: live_dir,
    )


def _patch_classifier_cohesive(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []

    def stub(*_a: object, **_k: object) -> str:
        calls.append(1)
        return "cohesive-cleanup"

    monkeypatch.setattr("continuous_refactoring.loop.classify_target", stub)
    return calls


def _patch_classifier_trap(monkeypatch: pytest.MonkeyPatch) -> None:
    def trap(*_a: object, **_k: object) -> object:
        raise AssertionError("classify_target must not be called during migration tick")

    monkeypatch.setattr("continuous_refactoring.loop.classify_target", trap)


def _patch_check_ready(
    monkeypatch: pytest.MonkeyPatch, verdict: str, reason: str = "",
) -> list[str]:
    calls: list[str] = []

    def fake(phase: object, manifest: object, *_a: object, **_k: object) -> tuple[str, str]:
        calls.append(getattr(phase, "name", ""))
        return (verdict, reason or verdict)

    monkeypatch.setattr("continuous_refactoring.loop.check_phase_ready", fake)
    return calls


def _patch_execute_phase(
    monkeypatch: pytest.MonkeyPatch,
    status: str = "done",
    reason: str = "ok",
) -> list[str]:
    calls: list[str] = []

    def fake(
        phase: object, manifest: object, target: object,
        taste: object, repo_root: object, live_dir: object,
        artifacts: object, **kwargs: object,
    ) -> ExecutePhaseOutcome:
        calls.append(getattr(phase, "name", ""))
        m = manifest  # type: ignore[assignment]
        updated_phases = tuple(
            replace(p, done=True) if i == m.current_phase else p
            for i, p in enumerate(m.phases)
        )
        updated = replace(
            m,
            phases=updated_phases,
            current_phase=m.current_phase + 1,
            last_touch=_utc_now().isoformat(timespec="milliseconds"),
        )
        mp = migration_root(Path(str(live_dir)), m.name) / "manifest.json"
        save_manifest(updated, mp)
        return ExecutePhaseOutcome(status=status, reason=reason)  # type: ignore[arg-type]

    monkeypatch.setattr("continuous_refactoring.loop.execute_phase", fake)
    return calls


def _patch_execute_phase_trap(monkeypatch: pytest.MonkeyPatch) -> None:
    def trap(*_a: object, **_k: object) -> object:
        raise AssertionError("execute_phase must not be called")

    monkeypatch.setattr("continuous_refactoring.loop.execute_phase", trap)


def _patch_one_shot(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    prompts: list[str] = []

    def capture(**kwargs: object) -> CommandCapture:
        prompts.append(str(kwargs.get("prompt", "")))
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", capture)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)
    return prompts


# ---------------------------------------------------------------------------
# Test 1: single eligible + ready migration advances one phase
# ---------------------------------------------------------------------------


def test_eligible_ready_migration_advances_phase(
    run_once_env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = run_once_env / ".migrations"
    live_dir.mkdir()

    now = _utc_now()
    manifest = _make_manifest("rework-auth", last_touch=now - timedelta(hours=24))
    manifest_path = _save(manifest, live_dir)
    _git_commit_all(run_once_env)

    _patch_live_dir(monkeypatch, live_dir)
    _patch_classifier_trap(monkeypatch)
    check_calls = _patch_check_ready(monkeypatch, "yes")
    exec_calls = _patch_execute_phase(monkeypatch, status="done")
    _patch_one_shot(monkeypatch)

    args = make_run_once_args(run_once_env)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0
    assert check_calls == ["setup"]
    assert exec_calls == ["setup"]

    continuous_refactoring.run_command(
        ["git", "checkout", "migration/rework-auth/phase-0-setup"],
        cwd=run_once_env,
    )
    reloaded = load_manifest(manifest_path)
    assert reloaded.phases[0].done is True
    assert reloaded.current_phase == 1


# ---------------------------------------------------------------------------
# Test 2: no eligible migrations → fall through to existing target path
# ---------------------------------------------------------------------------


def test_no_eligible_migrations_falls_through(
    run_once_env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = run_once_env / ".migrations"
    live_dir.mkdir()

    _patch_live_dir(monkeypatch, live_dir)
    classifier_calls = _patch_classifier_cohesive(monkeypatch)
    prompts = _patch_one_shot(monkeypatch)

    args = make_run_once_args(run_once_env)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0
    assert len(classifier_calls) == 1
    assert len(prompts) == 1


# ---------------------------------------------------------------------------
# Test 3: eligible but not ready → bumps wake_up_on, falls through
# ---------------------------------------------------------------------------


def test_eligible_not_ready_bumps_wake_up_on(
    run_once_env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = run_once_env / ".migrations"
    live_dir.mkdir()

    now = _utc_now()
    manifest = _make_manifest("rework-auth", last_touch=now - timedelta(hours=24))
    manifest_path = _save(manifest, live_dir)
    _git_commit_all(run_once_env)
    assert load_manifest(manifest_path).wake_up_on is None

    _patch_live_dir(monkeypatch, live_dir)
    classifier_calls = _patch_classifier_cohesive(monkeypatch)
    _patch_check_ready(monkeypatch, "no", "prerequisites not met")
    _patch_execute_phase_trap(monkeypatch)
    prompts = _patch_one_shot(monkeypatch)

    args = make_run_once_args(run_once_env)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0

    reloaded = load_manifest(manifest_path)
    assert reloaded.wake_up_on is not None
    assert reloaded.phases[0].done is False
    assert reloaded.current_phase == 0

    assert len(classifier_calls) == 1
    assert len(prompts) == 1


# ---------------------------------------------------------------------------
# Test 4: 6h safety invariant — last_touch=now-1h, wake_up_on=now-1d
# ---------------------------------------------------------------------------


def test_6h_invariant_blocks_execution(
    run_once_env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = run_once_env / ".migrations"
    live_dir.mkdir()

    now = _utc_now()
    manifest = _make_manifest(
        "rework-auth",
        last_touch=now - timedelta(hours=1),
        wake_up_on=now - timedelta(days=1),
    )
    _save(manifest, live_dir)
    _git_commit_all(run_once_env)

    assert not eligible_now(manifest, now)

    _patch_live_dir(monkeypatch, live_dir)
    classifier_calls = _patch_classifier_cohesive(monkeypatch)
    _patch_execute_phase_trap(monkeypatch)
    prompts = _patch_one_shot(monkeypatch)

    args = make_run_once_args(run_once_env)
    exit_code = continuous_refactoring.run_once(args)

    assert exit_code == 0
    assert len(classifier_calls) == 1
    assert len(prompts) == 1
