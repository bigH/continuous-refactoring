from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

import continuous_refactoring
import continuous_refactoring.loop
from continuous_refactoring.artifacts import (
    CommandCapture,
    ContinuousRefactorError,
    create_run_artifacts,
)
from continuous_refactoring.config import default_taste_text
from continuous_refactoring.decisions import DecisionRecord, RouteOutcome
from continuous_refactoring.migrations import (
    MigrationManifest,
    PhaseSpec,
    eligible_now,
    load_manifest,
    migration_root,
    save_manifest,
)
from continuous_refactoring.phases import ExecutePhaseOutcome
from continuous_refactoring.migration_tick import (
    enumerate_eligible_manifests,
    try_migration_tick,
)

from conftest import (
    make_run_once_args,
    noop_agent,
    noop_tests,
)

_PHASE_0 = PhaseSpec(name="setup", file="phase-0-setup.md", done=False, precondition="always")
_PHASE_1 = PhaseSpec(name="migrate", file="phase-1-migrate.md", done=False, precondition="phase 0 done")


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
    current_phase: str = "setup",
    phases: tuple[PhaseSpec, ...] = (_PHASE_0, _PHASE_1),
    awaiting_human_review: bool = False,
    human_review_reason: str | None = None,
) -> MigrationManifest:
    ts = (created_at or _utc_now()).isoformat(timespec="milliseconds")
    return MigrationManifest(
        name=name,
        created_at=ts,
        last_touch=last_touch.isoformat(timespec="milliseconds"),
        wake_up_on=wake_up_on.isoformat(timespec="milliseconds") if wake_up_on else None,
        awaiting_human_review=awaiting_human_review,
        status="in-progress",
        current_phase=current_phase,
        phases=phases,
        human_review_reason=human_review_reason,
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

    monkeypatch.setattr("continuous_refactoring.routing_pipeline.classify_target", stub)
    return calls


def _assert_fell_through(
    classifier_calls: list[str], prompts: list[str],
) -> None:
    assert len(classifier_calls) == 1
    assert len(prompts) == 1


def _patch_classifier_trap(monkeypatch: pytest.MonkeyPatch) -> None:
    def trap(*_a: object, **_k: object) -> object:
        raise AssertionError("classify_target must not be called during migration tick")

    monkeypatch.setattr("continuous_refactoring.routing_pipeline.classify_target", trap)


def _patch_check_ready(
    monkeypatch: pytest.MonkeyPatch, verdict: str, reason: str = "",
) -> list[str]:
    calls: list[str] = []

    def fake(phase: object, manifest: object, *_a: object, **_k: object) -> tuple[str, str]:
        calls.append(getattr(phase, "name", ""))
        return (verdict, reason or verdict)

    monkeypatch.setattr("continuous_refactoring.migration_tick.check_phase_ready", fake)
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

    monkeypatch.setattr("continuous_refactoring.migration_tick.execute_phase", fake)
    return calls


def _patch_execute_phase_trap(monkeypatch: pytest.MonkeyPatch) -> None:
    def trap(*_a: object, **_k: object) -> object:
        raise AssertionError("execute_phase must not be called")

    monkeypatch.setattr("continuous_refactoring.migration_tick.execute_phase", trap)


def _patch_one_shot(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    prompts: list[str] = []

    def capture(**kwargs: object) -> CommandCapture:
        prompts.append(str(kwargs.get("prompt", "")))
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", capture)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)
    return prompts


def _tick(
    live_dir: Path,
    repo_root: Path,
    *,
    taste: str = "runtime taste",
    validation_command: str = "uv run pytest",
    max_attempts: int | None = 3,
    attempt: int = 7,
    finalize_commit: Callable[..., object] | None = None,
) -> tuple[RouteOutcome, DecisionRecord | None]:
    artifacts = create_run_artifacts(
        repo_root=repo_root,
        agent="codex",
        model="fake-model",
        effort="xhigh",
        test_command=validation_command,
    )

    def noop_finalize(*_args: object, **_kwargs: object) -> None:
        return None

    return try_migration_tick(
        live_dir,
        taste,
        repo_root,
        artifacts,
        agent="codex",
        model="fake-model",
        effort="xhigh",
        timeout=123,
        commit_message_prefix="continuous refactor",
        validation_command=validation_command,
        max_attempts=max_attempts,
        attempt=attempt,
        finalize_commit=finalize_commit or noop_finalize,
    )


def test_enumerate_eligible_manifests_ignores_noise_and_sorts_by_created_at(
    tmp_path: Path,
) -> None:
    missing_live_dir = tmp_path / "missing"
    assert enumerate_eligible_manifests(missing_live_dir, _utc_now()) == []

    live_dir = tmp_path / "live"
    live_dir.mkdir()
    (live_dir / "plain-file").write_text("ignore\n", encoding="utf-8")
    now = _utc_now()

    _save(
        _make_manifest("__internal", last_touch=now - timedelta(days=1)),
        live_dir,
    )
    _save(
        _make_manifest(
            "no-current-phase",
            last_touch=now - timedelta(days=1),
            current_phase="",
            phases=(),
        ),
        live_dir,
    )
    _save(
        _make_manifest(
            "awaiting-review",
            last_touch=now - timedelta(days=1),
            created_at=now - timedelta(hours=3),
            awaiting_human_review=True,
            human_review_reason="needs a person",
        ),
        live_dir,
    )
    _save(
        _make_manifest(
            "newer",
            last_touch=now - timedelta(days=1),
            created_at=now - timedelta(hours=1),
        ),
        live_dir,
    )
    _save(
        _make_manifest(
            "older",
            last_touch=now - timedelta(days=1),
            created_at=now - timedelta(hours=2),
        ),
        live_dir,
    )

    candidates = enumerate_eligible_manifests(live_dir, now)

    assert [manifest.name for manifest, _ in candidates] == ["older", "newer"]
    assert [path.parent.name for _, path in candidates] == ["older", "newer"]


def test_try_migration_tick_skips_migrations_awaiting_human_review(
    run_once_env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = _migrations_dir(run_once_env)
    now = _utc_now()
    _save(
        _make_manifest(
            "needs-review",
            last_touch=now - timedelta(days=1),
            created_at=now - timedelta(hours=2),
            awaiting_human_review=True,
            human_review_reason="needs explicit signoff",
        ),
        live_dir,
    )
    _save(
        _make_manifest(
            "ready-now",
            last_touch=now - timedelta(days=1),
            created_at=now - timedelta(hours=1),
        ),
        live_dir,
    )
    ready_calls = _patch_check_ready(monkeypatch, "yes")
    exec_calls = _patch_execute_phase(monkeypatch, status="done")

    outcome, record = _tick(live_dir, run_once_env)

    assert outcome == "commit"
    assert record is not None
    assert ready_calls == ["setup"]
    assert exec_calls == ["setup"]
    assert load_manifest(live_dir / "needs-review" / "manifest.json").awaiting_human_review is True
    assert load_manifest(live_dir / "ready-now" / "manifest.json").phases[0].done is True


def test_ready_check_error_abandons_with_sanitized_decision_record(
    run_once_env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir, _, _ = _seed_manifest(
        run_once_env,
        name="rework-auth",
        last_touch=_utc_now() - timedelta(hours=24),
    )
    noisy_error = (
        f"ready check failed at {run_once_env}/phase.md\n"
        "codex exec --noise\n"
        "/tmp/transient-detail"
    )

    def fail_ready(*_args: object, **_kwargs: object) -> tuple[str, str]:
        raise ContinuousRefactorError(noisy_error)

    monkeypatch.setattr(
        "continuous_refactoring.migration_tick.check_phase_ready",
        fail_ready,
    )
    _patch_execute_phase_trap(monkeypatch)

    outcome, record = _tick(live_dir, run_once_env)

    assert outcome == "abandon"
    assert record is not None
    assert record.decision == "abandon"
    assert record.call_role == "phase.ready-check"
    assert record.phase_reached == "phase.ready-check"
    assert record.summary == "ready check failed at <repo>/phase.md <tmp>"


def test_ready_phase_execution_receives_runtime_settings_and_commits_phase_file(
    run_once_env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir, _, _ = _seed_manifest(
        run_once_env,
        name="rework-auth",
        last_touch=_utc_now() - timedelta(hours=24),
    )
    captured: dict[str, object] = {}
    commits: list[str] = []

    def fake_execute(
        phase: PhaseSpec,
        manifest: MigrationManifest,
        taste: str,
        repo_root: Path,
        passed_live_dir: Path,
        artifacts: object,
        **kwargs: object,
    ) -> ExecutePhaseOutcome:
        captured.update(
            phase=phase.name,
            manifest=manifest.name,
            taste=taste,
            repo_root=repo_root,
            live_dir=passed_live_dir,
            validation_command=kwargs["validation_command"],
            max_attempts=kwargs["max_attempts"],
            attempt=kwargs["attempt"],
            retry=kwargs["retry"],
            agent=kwargs["agent"],
            model=kwargs["model"],
            effort=kwargs["effort"],
            timeout=kwargs["timeout"],
            artifacts=artifacts,
        )
        return ExecutePhaseOutcome(status="done", reason="ok")

    def finalize(
        repo_root: Path,
        head_before: str,
        commit_message: str,
        **kwargs: object,
    ) -> None:
        captured["finalize_repo_root"] = repo_root
        captured["finalize_head_before"] = head_before
        captured["finalize_phase"] = kwargs["phase"]
        commits.append(commit_message)

    _patch_check_ready(monkeypatch, "yes")
    monkeypatch.setattr(
        "continuous_refactoring.migration_tick.execute_phase",
        fake_execute,
    )

    outcome, record = _tick(
        live_dir,
        run_once_env,
        taste="specific runtime taste",
        validation_command="custom validation",
        max_attempts=5,
        attempt=11,
        finalize_commit=finalize,
    )

    assert outcome == "commit"
    assert record is not None
    assert record.decision == "commit"
    assert captured["phase"] == "setup"
    assert captured["manifest"] == "rework-auth"
    assert captured["taste"] == "specific runtime taste"
    assert captured["repo_root"] == run_once_env
    assert captured["live_dir"] == live_dir
    assert captured["validation_command"] == "custom validation"
    assert captured["max_attempts"] == 5
    assert captured["attempt"] == 11
    assert captured["retry"] == 1
    assert captured["agent"] == "codex"
    assert captured["model"] == "fake-model"
    assert captured["effort"] == "xhigh"
    assert captured["timeout"] == 123
    assert commits == ["continuous refactor: migration/rework-auth/phase-0-setup.md"]
    assert "phase-0/setup" not in commits[0]
    assert captured["finalize_repo_root"] == run_once_env
    assert captured["finalize_phase"] == "migration"


def test_failed_ready_phase_abandons_and_preserves_retry_used(
    run_once_env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir, _, _ = _seed_manifest(
        run_once_env,
        name="rework-auth",
        last_touch=_utc_now() - timedelta(hours=24),
    )

    def fake_execute(*_args: object, **_kwargs: object) -> ExecutePhaseOutcome:
        return ExecutePhaseOutcome(
            status="failed",
            reason=f"validation broke at {run_once_env}/phase.md",
            call_role="phase.validation",
            phase_reached="phase.validation",
            failure_kind="validation-failed",
            retry=4,
        )

    def finalize_trap(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("failed phase execution must not be committed")

    _patch_check_ready(monkeypatch, "yes")
    monkeypatch.setattr(
        "continuous_refactoring.migration_tick.execute_phase",
        fake_execute,
    )

    outcome, record = _tick(
        live_dir,
        run_once_env,
        finalize_commit=finalize_trap,
    )

    assert outcome == "abandon"
    assert record is not None
    assert record.decision == "abandon"
    assert record.call_role == "phase.validation"
    assert record.phase_reached == "phase.validation"
    assert record.failure_kind == "validation-failed"
    assert record.summary == "validation broke at <repo>/phase.md"
    assert record.retry_used == 4


def test_not_ready_phase_defers_without_overwriting_existing_wake_up(
    run_once_env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = _utc_now()
    existing_wake = now - timedelta(hours=1)
    live_dir, _, manifest_path = _seed_manifest(
        run_once_env,
        name="rework-auth",
        last_touch=now - timedelta(hours=24),
        wake_up_on=existing_wake,
    )

    _patch_check_ready(monkeypatch, "no", f"waiting on {run_once_env}/fixture")
    _patch_execute_phase_trap(monkeypatch)

    outcome, record = _tick(live_dir, run_once_env)

    reloaded = load_manifest(manifest_path)
    assert outcome == "not-routed"
    assert record is not None
    assert record.decision == "retry"
    assert record.call_role == "phase.ready-check"
    assert record.summary == "waiting on <repo>/fixture"
    assert datetime.fromisoformat(reloaded.last_touch) > now - timedelta(hours=24)
    assert reloaded.cooldown_until is not None
    assert datetime.fromisoformat(reloaded.cooldown_until) > now
    assert reloaded.wake_up_on == existing_wake.isoformat(timespec="milliseconds")
    assert reloaded.awaiting_human_review is False


def test_unverifiable_phase_blocks_and_persists_human_review_fields(
    run_once_env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir, _, manifest_path = _seed_manifest(
        run_once_env,
        name="rework-auth",
        last_touch=_utc_now() - timedelta(hours=24),
    )
    reason = f"requires manual check in {run_once_env}/external-system"

    _patch_check_ready(monkeypatch, "unverifiable", reason)
    _patch_execute_phase_trap(monkeypatch)

    outcome, record = _tick(live_dir, run_once_env)

    reloaded = load_manifest(manifest_path)
    assert outcome == "blocked"
    assert record is not None
    assert record.decision == "blocked"
    assert record.retry_recommendation == "human-review"
    assert record.call_role == "phase.ready-check"
    assert record.failure_kind == "phase-ready-unverifiable"
    assert record.summary == "requires manual check in <repo>/external-system"
    assert reloaded.awaiting_human_review is True
    assert reloaded.human_review_reason == reason
    assert reloaded.cooldown_until is not None
    assert reloaded.wake_up_on is not None


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
    assert eligible_now(reloaded, _utc_now()) is True


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


def test_phase_ready_check_receives_runtime_taste(
    run_once_env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = _utc_now()
    live_dir, _, _ = _seed_manifest(
        run_once_env,
        name="rework-auth",
        last_touch=now - timedelta(hours=24),
        commit=True,
    )
    captured_taste: list[str] = []

    def fake_check_ready(
        phase: object,
        manifest: object,
        repo_root: object,
        artifacts: object,
        *,
        taste: str = "",
        **kwargs: object,
    ) -> tuple[str, str]:
        captured_taste.append(taste)
        return ("no", "not ready")

    _patch_live_dir(monkeypatch, live_dir)
    _patch_classifier_cohesive(monkeypatch)
    monkeypatch.setattr(
        "continuous_refactoring.migration_tick.check_phase_ready",
        fake_check_ready,
    )
    _patch_execute_phase_trap(monkeypatch)
    _patch_one_shot(monkeypatch)

    exit_code = _run_once(run_once_env)

    assert exit_code == 0
    assert captured_taste == [default_taste_text()]


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
    assert reloaded.cooldown_until is not None
    assert reloaded.phases[0].done is False
    assert reloaded.current_phase == "setup"
    assert eligible_now(reloaded, _utc_now()) is False

    _assert_fell_through(classifier_calls, prompts)


# ---------------------------------------------------------------------------
# Test 4: future wake_up_on still blocks execution
# ---------------------------------------------------------------------------


def test_future_wake_up_blocks_execution(
    run_once_env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = _utc_now()
    live_dir, manifest, _ = _seed_manifest(
        run_once_env,
        name="rework-auth",
        last_touch=now - timedelta(hours=1),
        wake_up_on=now + timedelta(days=1),
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
