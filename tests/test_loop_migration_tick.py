from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

import continuous_refactoring
import continuous_refactoring.loop
from continuous_refactoring.artifacts import CommandCapture, ContinuousRefactorError
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
    make_run_once_args,
    noop_agent,
    noop_tests,
)

_PHASE_0 = PhaseSpec(name="setup", file="phase-0-setup.md", done=False, ready_when="always")
_PHASE_1 = PhaseSpec(name="migrate", file="phase-1-migrate.md", done=False, ready_when="phase 0 done")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _migrations_dir(run_once_env: Path) -> Path:
    live_dir = run_once_env / ".migrations"
    live_dir.mkdir()
    return live_dir


def _run_once(run_once_env: Path) -> int:
    return continuous_refactoring.run_once(make_run_once_args(run_once_env))


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
        current_phase="setup",
        phases=(_PHASE_0, _PHASE_1),
    )


def _save(manifest: MigrationManifest, live_dir: Path) -> Path:
    root = migration_root(live_dir, manifest.name)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "manifest.json"
    save_manifest(manifest, path)
    return path


def _seed_manifest(
    run_once_env: Path,
    *,
    name: str,
    last_touch: datetime,
    wake_up_on: datetime | None = None,
    created_at: datetime | None = None,
    commit: bool = False,
) -> tuple[Path, MigrationManifest, Path]:
    live_dir = _migrations_dir(run_once_env)
    manifest = _make_manifest(
        name,
        last_touch=last_touch,
        wake_up_on=wake_up_on,
        created_at=created_at,
    )
    path = _save(manifest, live_dir)
    if commit:
        _git_commit_all(run_once_env)
    return live_dir, manifest, path


def _patch_live_dir(
    monkeypatch: pytest.MonkeyPatch, live_dir: Path,
) -> None:
    monkeypatch.setattr(
        "continuous_refactoring.loop._resolve_live_migrations_dir",
        lambda _: live_dir,
    )


def _patch_classifier_cohesive(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def stub(*_a: object, **_k: object) -> str:
        target = _a[0] if _a else None
        if target is None:
            calls.append("")
        else:
            calls.append(getattr(target, "description", ""))
        return "cohesive-cleanup"

    monkeypatch.setattr("continuous_refactoring.loop.classify_target", stub)
    return calls


def _assert_fell_through(
    classifier_calls: list[str], prompts: list[str],
) -> None:
    assert len(classifier_calls) == 1
    assert len(prompts) == 1


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
        phase: PhaseSpec, manifest: MigrationManifest,
        taste: object, repo_root: object, live_dir: Path,
        artifacts: object, **kwargs: object,
    ) -> ExecutePhaseOutcome:
        calls.append(phase.name)
        phase_index = next(
            index
            for index, manifest_phase in enumerate(manifest.phases)
            if manifest_phase.name == phase.name
        )
        updated_phases = tuple(
            replace(p, done=True) if i == phase_index else p
            for i, p in enumerate(manifest.phases)
        )
        next_phase_name = (
            manifest.phases[phase_index + 1].name
            if phase_index + 1 < len(manifest.phases)
            else ""
        )
        updated = replace(
            manifest,
            phases=updated_phases,
            current_phase=next_phase_name,
            status="done" if next_phase_name == "" else manifest.status,
            last_touch=_utc_now().isoformat(timespec="milliseconds"),
        )
        mp = migration_root(live_dir, manifest.name) / "manifest.json"
        save_manifest(updated, mp)
        return ExecutePhaseOutcome(status=status, reason=reason)

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
    now = _utc_now()
    live_dir, _, manifest_path = _seed_manifest(
        run_once_env,
        name="rework-auth",
        last_touch=now - timedelta(hours=24),
        commit=True,
    )

    _patch_live_dir(monkeypatch, live_dir)
    _patch_classifier_trap(monkeypatch)
    check_calls = _patch_check_ready(monkeypatch, "yes")
    exec_calls = _patch_execute_phase(monkeypatch, status="done")
    _patch_one_shot(monkeypatch)

    exit_code = _run_once(run_once_env)

    assert exit_code == 0
    assert check_calls == ["setup"]
    assert exec_calls == ["setup"]

    reloaded = load_manifest(manifest_path)
    assert reloaded.phases[0].done is True
    assert reloaded.current_phase == "migrate"


def test_migration_labels_use_phase_file_not_numeric_cursor(
    run_once_env: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    now = _utc_now()
    live_dir, _, _ = _seed_manifest(
        run_once_env,
        name="rework-auth",
        last_touch=now - timedelta(hours=24),
        commit=True,
    )

    commit_messages: list[str] = []

    _patch_live_dir(monkeypatch, live_dir)
    _patch_classifier_trap(monkeypatch)
    _patch_check_ready(monkeypatch, "yes")
    _patch_execute_phase(monkeypatch, status="done")
    _patch_one_shot(monkeypatch)
    monkeypatch.setattr(
        "continuous_refactoring.loop._finalize_commit",
        lambda _repo_root, _head_before, message, **_kwargs: commit_messages.append(message),
    )

    exit_code = _run_once(run_once_env)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "phase-0/setup" not in out
    assert "phase-0/setup" not in commit_messages[0]
    assert "phase-0-setup.md" in out
    assert "migration/rework-auth/phase-0-setup.md" in commit_messages[0]


# ---------------------------------------------------------------------------
# Test 2: no eligible migrations → fall through to existing target path
# ---------------------------------------------------------------------------


def test_no_eligible_migrations_falls_through(
    run_once_env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = _migrations_dir(run_once_env)

    _patch_live_dir(monkeypatch, live_dir)
    classifier_calls = _patch_classifier_cohesive(monkeypatch)
    prompts = _patch_one_shot(monkeypatch)

    exit_code = _run_once(run_once_env)

    assert exit_code == 0
    _assert_fell_through(classifier_calls, prompts)


# ---------------------------------------------------------------------------
# Test 3: eligible but not ready → bumps wake_up_on, falls through
# ---------------------------------------------------------------------------


def test_eligible_not_ready_bumps_wake_up_on(
    run_once_env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = _utc_now()
    live_dir, _, manifest_path = _seed_manifest(
        run_once_env,
        name="rework-auth",
        last_touch=now - timedelta(hours=24),
        commit=True,
    )
    assert load_manifest(manifest_path).wake_up_on is None

    _patch_live_dir(monkeypatch, live_dir)
    classifier_calls = _patch_classifier_cohesive(monkeypatch)
    _patch_check_ready(monkeypatch, "no", "prerequisites not met")
    _patch_execute_phase_trap(monkeypatch)
    prompts = _patch_one_shot(monkeypatch)

    exit_code = _run_once(run_once_env)

    assert exit_code == 0

    reloaded = load_manifest(manifest_path)
    assert reloaded.wake_up_on is not None
    assert reloaded.phases[0].done is False
    assert reloaded.current_phase == "setup"

    _assert_fell_through(classifier_calls, prompts)


# ---------------------------------------------------------------------------
# Test 4: 6h safety invariant — last_touch=now-1h, wake_up_on=now-1d
# ---------------------------------------------------------------------------


def test_6h_invariant_blocks_execution(
    run_once_env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = _utc_now()
    live_dir, manifest, _ = _seed_manifest(
        run_once_env,
        name="rework-auth",
        last_touch=now - timedelta(hours=1),
        wake_up_on=now - timedelta(days=1),
        commit=True,
    )

    assert not eligible_now(manifest, now)

    _patch_live_dir(monkeypatch, live_dir)
    classifier_calls = _patch_classifier_cohesive(monkeypatch)
    _patch_execute_phase_trap(monkeypatch)
    prompts = _patch_one_shot(monkeypatch)

    exit_code = _run_once(run_once_env)

    assert exit_code == 0
    _assert_fell_through(classifier_calls, prompts)


def test_unverifiable_phase_stores_human_review_reason(
    run_once_env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pytest

    now = _utc_now()
    live_dir, _, manifest_path = _seed_manifest(
        run_once_env,
        name="rework-auth",
        last_touch=now - timedelta(hours=24),
        commit=True,
    )

    reason = "hit external dependency — can't check locally"
    _patch_live_dir(monkeypatch, live_dir)
    _patch_classifier_cohesive(monkeypatch)
    _patch_check_ready(monkeypatch, "unverifiable", reason)
    _patch_execute_phase_trap(monkeypatch)
    _patch_one_shot(monkeypatch)

    with pytest.raises(ContinuousRefactorError, match="external dependency"):
        _run_once(run_once_env)

    reloaded = load_manifest(manifest_path)
    assert reloaded.awaiting_human_review is True
    assert reloaded.human_review_reason == reason


def test_empty_current_phase_skips_migration_path(
    run_once_env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = _utc_now()
    live_dir, manifest, manifest_path = _seed_manifest(
        run_once_env,
        name="rework-auth",
        last_touch=now - timedelta(hours=24),
        commit=False,
    )
    manifest = replace(manifest, current_phase="")
    save_manifest(manifest, manifest_path)
    _git_commit_all(run_once_env)

    _patch_live_dir(monkeypatch, live_dir)
    check_calls = _patch_check_ready(monkeypatch, "yes")
    _patch_execute_phase_trap(monkeypatch)
    classifier_calls = _patch_classifier_cohesive(monkeypatch)
    prompts = _patch_one_shot(monkeypatch)

    exit_code = _run_once(run_once_env)

    assert exit_code == 0
    assert check_calls == []
    _assert_fell_through(classifier_calls, prompts)

    reloaded = load_manifest(manifest_path)
    assert reloaded.current_phase == ""
