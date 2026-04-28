from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import continuous_refactoring
from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.cli import build_parser
from continuous_refactoring.decisions import DecisionRecord, RouteOutcome
from continuous_refactoring.effort import EffortBudget
from continuous_refactoring.migrations import (
    MigrationManifest,
    PhaseSpec,
    load_manifest,
    migration_root,
    save_manifest,
)

from conftest import make_run_loop_args


_PHASE = PhaseSpec(
    name="setup", file="phase-0-setup.md", done=False, precondition="always",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _seed_manifest(
    live_dir: Path,
    name: str,
    *,
    last_touch: datetime | None = None,
    awaiting_review: bool = False,
    current_phase: str = "setup",
    phases: tuple[PhaseSpec, ...] = (_PHASE,),
    wake_up_on: datetime | None = None,
    cooldown_until: datetime | None = None,
) -> Path:
    lt = (last_touch or _utc_now() - timedelta(days=1)).isoformat(
        timespec="milliseconds",
    )
    manifest = MigrationManifest(
        name=name,
        created_at=(_utc_now() - timedelta(days=2)).isoformat(timespec="milliseconds"),
        last_touch=lt,
        wake_up_on=wake_up_on.isoformat(timespec="milliseconds") if wake_up_on else None,
        awaiting_human_review=awaiting_review,
        status="ready",
        current_phase=current_phase,
        phases=phases,
        cooldown_until=(
            cooldown_until.isoformat(timespec="milliseconds")
            if cooldown_until is not None
            else None
        ),
    )
    root = migration_root(live_dir, name)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "manifest.json"
    save_manifest(manifest, path)
    return path


def _mark_done(path: Path) -> None:
    manifest = load_manifest(path)
    updated = replace(
        manifest,
        status="done",
        current_phase="",
        last_touch=_utc_now().isoformat(timespec="milliseconds"),
    )
    save_manifest(updated, path)


def _flag_for_review(path: Path) -> None:
    manifest = load_manifest(path)
    updated = replace(
        manifest,
        awaiting_human_review=True,
        last_touch=_utc_now().isoformat(timespec="milliseconds"),
    )
    save_manifest(updated, path)


def _commit_ok(target: str) -> DecisionRecord:
    return DecisionRecord(
        decision="commit",
        retry_recommendation="none",
        target=target,
        call_role="phase.execute",
        phase_reached="phase.execute",
        failure_kind="none",
        summary="ok",
    )


def _abandon(target: str) -> DecisionRecord:
    return DecisionRecord(
        decision="abandon",
        retry_recommendation="new-target",
        target=target,
        call_role="phase.execute",
        phase_reached="phase.execute",
        failure_kind="phase-failed",
        summary="boom",
    )


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


def test_run_parser_accepts_focus_on_live_migrations() -> None:
    args = build_parser().parse_args(
        [
            "run",
            "--with", "claude",
            "--model", "opus",
            "--validation-command", "uv run pytest",
            "--focus-on-live-migrations",
        ],
    )
    assert args.focus_on_live_migrations is True


def test_run_parser_focus_flag_defaults_false() -> None:
    args = build_parser().parse_args(
        [
            "run",
            "--with", "claude",
            "--model", "opus",
            "--validation-command", "uv run pytest",
            "--max-refactors", "1",
            "--scope-instruction", "s",
        ],
    )
    assert args.focus_on_live_migrations is False


def test_focused_loop_eligibility_rechecks_effort_deferred_phase_when_cap_rises(
    tmp_path: Path,
) -> None:
    live_dir = tmp_path / "live-migrations"
    live_dir.mkdir()
    high_phase = replace(_PHASE, required_effort="xhigh")
    cooldown_until = _utc_now() + timedelta(hours=5)
    _seed_manifest(
        live_dir,
        "high-effort",
        phases=(high_phase,),
        cooldown_until=cooldown_until,
    )

    low_budget = EffortBudget(default_effort="high", max_allowed_effort="high")
    high_budget = EffortBudget(default_effort="high", max_allowed_effort="xhigh")

    assert continuous_refactoring.loop._focus_eligible_manifests(
        live_dir,
        _utc_now(),
        low_budget,
    ) == []
    assert [
        manifest.name
        for manifest, _ in continuous_refactoring.loop._focus_eligible_manifests(
            live_dir,
            _utc_now(),
            high_budget,
        )
    ] == ["high-effort"]


# ---------------------------------------------------------------------------
# _handle_run guard tests
# ---------------------------------------------------------------------------


def _make_handle_run_args(
    repo_root: Path, *, focus: bool,
) -> argparse.Namespace:
    return argparse.Namespace(
        agent="claude",
        model="opus",
        effort="medium",
        validation_command="uv run pytest",
        extensions=None,
        globs=None,
        targets=None,
        paths=None,
        scope_instruction=None,
        timeout=None,
        refactoring_prompt=None,
        fix_prompt=None,
        show_agent_logs=False,
        show_command_logs=False,
        repo_root=repo_root,
        max_attempts=None,
        max_refactors=None,
        commit_message_prefix="continuous refactor",
        max_consecutive_failures=3,
        sleep=0.0,
        focus_on_live_migrations=focus,
    )


def test_handle_run_without_focus_requires_targeting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    args = _make_handle_run_args(repo_root, focus=False)

    from continuous_refactoring.cli import _handle_run

    with pytest.raises(SystemExit) as exc:
        _handle_run(args)
    assert exc.value.code == 2


def test_handle_run_with_focus_bypasses_targeting_and_max_refactors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    args = _make_handle_run_args(repo_root, focus=True)

    calls: list[argparse.Namespace] = []

    def fake_focus(passed: argparse.Namespace) -> int:
        calls.append(passed)
        return 0

    monkeypatch.setattr(
        "continuous_refactoring.cli.run_migrations_focused_loop", fake_focus,
    )

    from continuous_refactoring.cli import _handle_run

    with pytest.raises(SystemExit) as exc:
        _handle_run(args)
    assert exc.value.code == 0
    assert len(calls) == 1
    assert calls[0].focus_on_live_migrations is True


# ---------------------------------------------------------------------------
# run_migrations_focused_loop behavior tests
# ---------------------------------------------------------------------------


def _install_focused_loop_env(
    run_loop_env: Path, monkeypatch: pytest.MonkeyPatch, live_dir: Path,
) -> None:
    from conftest import noop_tests

    monkeypatch.setattr(
        "continuous_refactoring.loop._resolve_live_migrations_dir",
        lambda _repo_root: live_dir,
    )
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)


def test_focused_loop_exits_zero_when_no_live_migrations_remain(
    run_loop_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = tmp_path / "live-migrations"
    live_dir.mkdir()
    _install_focused_loop_env(run_loop_env, monkeypatch, live_dir)

    args = make_run_loop_args(
        run_loop_env, focus_on_live_migrations=True,
    )
    exit_code = continuous_refactoring.run_migrations_focused_loop(args)
    assert exit_code == 0


def test_focused_loop_raises_when_live_dir_unconfigured(
    run_loop_env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "continuous_refactoring.loop._resolve_live_migrations_dir",
        lambda _repo_root: None,
    )

    args = make_run_loop_args(
        run_loop_env, focus_on_live_migrations=True,
    )
    with pytest.raises(ContinuousRefactorError, match="no live-migrations-dir"):
        continuous_refactoring.run_migrations_focused_loop(args)


def test_focused_loop_ticks_each_eligible_migration_until_done(
    run_loop_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = tmp_path / "live-migrations"
    live_dir.mkdir()
    alpha_path = _seed_manifest(live_dir, "alpha")
    beta_path = _seed_manifest(live_dir, "beta")

    _install_focused_loop_env(run_loop_env, monkeypatch, live_dir)

    tick_calls: list[str] = []
    remaining = {"alpha": alpha_path, "beta": beta_path}

    def fake_tick(
        live_dir: Path, taste: str, repo_root: Path, artifacts: object,
        **_kwargs: object,
    ) -> tuple[RouteOutcome, DecisionRecord | None]:
        name, path = next(iter(remaining.items()))
        remaining.pop(name)
        tick_calls.append(name)
        _mark_done(path)
        return ("commit", _commit_ok(f"migration/{name}"))

    monkeypatch.setattr(
        "continuous_refactoring.migration_tick.try_migration_tick", fake_tick,
    )

    args = make_run_loop_args(
        run_loop_env, focus_on_live_migrations=True,
    )
    exit_code = continuous_refactoring.run_migrations_focused_loop(args)

    assert exit_code == 0
    assert tick_calls == ["alpha", "beta"]


def test_focused_loop_tick_header_lists_repo_relative_phase_files(
    run_loop_env: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    live_dir = run_loop_env / "migrations"
    live_dir.mkdir()
    alpha_path = _seed_manifest(live_dir, "alpha")
    beta_path = _seed_manifest(live_dir, "beta")
    continuous_refactoring.run_command(["git", "add", "migrations"], cwd=run_loop_env)
    continuous_refactoring.run_command(
        ["git", "commit", "-m", "seed migrations"],
        cwd=run_loop_env,
    )

    _install_focused_loop_env(run_loop_env, monkeypatch, live_dir)

    remaining = {"alpha": alpha_path, "beta": beta_path}

    def fake_tick(
        live_dir: Path, taste: str, repo_root: Path, artifacts: object,
        **_kwargs: object,
    ) -> tuple[RouteOutcome, DecisionRecord | None]:
        name, path = next(iter(remaining.items()))
        remaining.pop(name)
        _mark_done(path)
        return ("commit", _commit_ok(f"migration/{name}"))

    monkeypatch.setattr(
        "continuous_refactoring.migration_tick.try_migration_tick",
        fake_tick,
    )

    args = make_run_loop_args(
        run_loop_env,
        focus_on_live_migrations=True,
    )
    assert continuous_refactoring.run_migrations_focused_loop(args) == 0

    captured = capsys.readouterr()
    assert (
        "── Migration tick 1 (eligible: "
        "migrations/alpha/phase-0-setup.md, "
        "migrations/beta/phase-0-setup.md) ──"
    ) in captured.out
    assert "eligible: alpha, beta" not in captured.out


def test_focused_loop_advances_multiple_ready_phases_until_deferred(
    run_loop_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    live_dir = tmp_path / "live-migrations"
    live_dir.mkdir()
    migrate_phase = PhaseSpec(
        name="migrate",
        file="phase-1-migrate.md",
        done=False,
        precondition="setup done",
    )
    manifest_path = _seed_manifest(
        live_dir,
        "multi-step",
        phases=(_PHASE, migrate_phase),
    )

    _install_focused_loop_env(run_loop_env, monkeypatch, live_dir)

    ready_calls: list[str] = []
    execute_calls: list[str] = []

    def fake_ready(
        phase: PhaseSpec,
        manifest: MigrationManifest,
        *_args: object,
        **_kwargs: object,
    ) -> tuple[str, str]:
        ready_calls.append(phase.name)
        if phase.name == "setup":
            return ("yes", "ready")
        return ("no", "wait for follow-up")

    def fake_execute(
        phase: PhaseSpec,
        manifest: MigrationManifest,
        taste: str,
        repo_root: Path,
        live_dir: Path,
        artifacts: object,
        **kwargs: object,
    ) -> object:
        execute_calls.append(phase.name)
        assert kwargs["validation_command"]
        assert kwargs["max_attempts"] == 1
        updated = replace(
            manifest,
            phases=(replace(manifest.phases[0], done=True), manifest.phases[1]),
            current_phase="migrate",
            last_touch=_utc_now().isoformat(timespec="milliseconds"),
            wake_up_on=None,
            cooldown_until=None,
        )
        save_manifest(updated, manifest_path)
        from continuous_refactoring.phases import ExecutePhaseOutcome

        return ExecutePhaseOutcome(status="done", reason="ok")

    monkeypatch.setattr("continuous_refactoring.migration_tick.check_phase_ready", fake_ready)
    monkeypatch.setattr("continuous_refactoring.migration_tick.execute_phase", fake_execute)
    monkeypatch.setattr(
        "continuous_refactoring.loop._finalize_commit",
        lambda *_args, **_kwargs: None,
    )

    args = make_run_loop_args(
        run_loop_env,
        focus_on_live_migrations=True,
    )
    exit_code = continuous_refactoring.run_migrations_focused_loop(args)

    assert exit_code == 0
    assert ready_calls == ["setup", "migrate"]
    assert execute_calls == ["setup"]
    reloaded = load_manifest(manifest_path)
    assert reloaded.current_phase == "migrate"
    assert reloaded.cooldown_until is not None
    assert reloaded.wake_up_on is not None
    captured = capsys.readouterr()
    assert "Migration tick deferred all eligible migrations: wait for follow-up" in captured.out



def test_focused_loop_terminates_when_only_awaiting_human_review_remains(
    run_loop_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = tmp_path / "live-migrations"
    live_dir.mkdir()
    only_path = _seed_manifest(live_dir, "needs-review")

    _install_focused_loop_env(run_loop_env, monkeypatch, live_dir)

    tick_calls: list[str] = []

    def fake_tick(
        live_dir: Path, taste: str, repo_root: Path, artifacts: object,
        **_kwargs: object,
    ) -> tuple[RouteOutcome, DecisionRecord | None]:
        tick_calls.append("needs-review")
        _flag_for_review(only_path)
        return (
            "blocked",
            DecisionRecord(
                decision="blocked",
                retry_recommendation="human-review",
                target="migration/needs-review",
                call_role="phase.ready-check",
                phase_reached="phase.ready-check",
                failure_kind="phase-ready-unverifiable",
                summary="awaiting human",
            ),
        )

    monkeypatch.setattr(
        "continuous_refactoring.migration_tick.try_migration_tick", fake_tick,
    )

    args = make_run_loop_args(
        run_loop_env,
        focus_on_live_migrations=True,
        max_consecutive_failures=5,
    )
    exit_code = continuous_refactoring.run_migrations_focused_loop(args)

    assert exit_code == 0
    assert tick_calls == ["needs-review"]


def test_focused_loop_reports_deferred_phase_reason(
    run_loop_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    live_dir = tmp_path / "live-migrations"
    live_dir.mkdir()
    _seed_manifest(live_dir, "deferred")

    _install_focused_loop_env(run_loop_env, monkeypatch, live_dir)

    def fake_tick(
        live_dir: Path, taste: str, repo_root: Path, artifacts: object,
        **_kwargs: object,
    ) -> tuple[RouteOutcome, DecisionRecord | None]:
        return (
            "not-routed",
            DecisionRecord(
                decision="retry",
                retry_recommendation="same-target",
                target="migration/deferred",
                call_role="phase.ready-check",
                phase_reached="phase.ready-check",
                failure_kind="phase-ready-no",
                summary="phase spec contradicts repo invariants",
            ),
        )

    monkeypatch.setattr(
        "continuous_refactoring.migration_tick.try_migration_tick", fake_tick,
    )

    args = make_run_loop_args(
        run_loop_env, focus_on_live_migrations=True,
    )
    exit_code = continuous_refactoring.run_migrations_focused_loop(args)

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Migration tick deferred all eligible migrations" in captured.out
    assert "phase spec contradicts repo invariants" in captured.out


def test_focused_loop_aborts_after_max_consecutive_failures(
    run_loop_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = tmp_path / "live-migrations"
    live_dir.mkdir()
    sticky_path = _seed_manifest(live_dir, "sticky")

    _install_focused_loop_env(run_loop_env, monkeypatch, live_dir)

    tick_calls: list[int] = []

    def fake_tick(
        live_dir: Path, taste: str, repo_root: Path, artifacts: object,
        **_kwargs: object,
    ) -> tuple[RouteOutcome, DecisionRecord | None]:
        tick_calls.append(len(tick_calls) + 1)
        manifest = load_manifest(sticky_path)
        save_manifest(
            replace(
                manifest,
                last_touch=(_utc_now() - timedelta(days=1)).isoformat(
                    timespec="milliseconds",
                ),
            ),
            sticky_path,
        )
        return ("abandon", _abandon("migration/sticky"))

    monkeypatch.setattr(
        "continuous_refactoring.migration_tick.try_migration_tick", fake_tick,
    )

    args = make_run_loop_args(
        run_loop_env,
        focus_on_live_migrations=True,
        max_consecutive_failures=2,
    )
    with pytest.raises(ContinuousRefactorError, match="2 consecutive failures"):
        continuous_refactoring.run_migrations_focused_loop(args)

    assert len(tick_calls) == 2
