from __future__ import annotations

import json
from pathlib import Path

import pytest

import continuous_refactoring
import continuous_refactoring.git
import continuous_refactoring.loop
from continuous_refactoring.migrations import (
    MigrationManifest,
    PhaseSpec,
    save_manifest,
)

from conftest import (
    make_run_loop_args,
    make_run_once_args,
    noop_agent,
    noop_tests,
)


_BRANCHING_TOKENS = ("checkout", "switch")
_BRANCHING_PAIRS = (
    ("checkout", "-b"),
    ("branch", "-c"),
    ("branch", "-D"),
)


def _is_branching_argv(argv: tuple[str, ...]) -> bool:
    if not argv or argv[0] != "git":
        return False
    rest = argv[1:]
    if any(token in rest for token in _BRANCHING_TOKENS):
        return True
    adjacent_pairs = set(zip(rest, rest[1:]))
    return any(pair in adjacent_pairs for pair in _BRANCHING_PAIRS)


def _install_argv_spy(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    """Record every argv passed to git.run_command across the driver."""
    captured: list[tuple[str, ...]] = []
    real_run_command = continuous_refactoring.git.run_command

    def spy(command, cwd, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured.append(tuple(command))
        return real_run_command(command, cwd, *args, **kwargs)

    # The driver imports run_command into multiple modules; patch each binding.
    monkeypatch.setattr("continuous_refactoring.git.run_command", spy)
    monkeypatch.setattr("continuous_refactoring.loop.run_command", spy)
    return captured


def _assert_no_branching(captured: list[tuple[str, ...]]) -> None:
    branching = [argv for argv in captured if _is_branching_argv(argv)]
    assert not branching, (
        "Driver invoked branching git commands: "
        + ", ".join(" ".join(argv) for argv in branching)
    )


def _seed_live_manifest(live_dir: Path, name: str = "auto-migration") -> None:
    manifest = MigrationManifest(
        name=name,
        created_at="2026-04-16T00:00:00.000+00:00",
        last_touch="2026-04-16T00:00:00.000+00:00",
        wake_up_on=None,
        awaiting_human_review=False,
        status="ready",
        current_phase="setup",
        phases=(
            PhaseSpec(
                name="setup",
                file="phase-0-setup.md",
                done=False,
                precondition="always",
            ),
        ),
    )
    migration_dir = live_dir / name
    migration_dir.mkdir(parents=True, exist_ok=True)
    save_manifest(manifest, migration_dir / "manifest.json")


def test_run_once_makes_no_branching_calls(
    run_once_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", noop_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    captured = _install_argv_spy(monkeypatch)

    exit_code = continuous_refactoring.run_once(make_run_once_args(run_once_env))

    assert exit_code == 0
    _assert_no_branching(captured)


def test_run_loop_makes_no_branching_calls(
    run_loop_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env

    def touching_agent(**kwargs: object) -> object:
        rr = Path(str(kwargs.get("repo_root", "")))
        (rr / "touched.txt").write_text("touched\n", encoding="utf-8")
        return noop_agent(**kwargs)

    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", touching_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    targets_file = tmp_path / "targets.jsonl"
    targets_file.write_text(
        "\n".join(
            json.dumps({"description": f"target-{i}", "files": [f"file{i}.py"]})
            for i in range(2)
        ),
        encoding="utf-8",
    )

    captured = _install_argv_spy(monkeypatch)

    exit_code = continuous_refactoring.run_loop(
        make_run_loop_args(
            repo_root,
            targets=targets_file,
            scope_instruction=None,
        )
    )

    assert exit_code == 0
    _assert_no_branching(captured)


def test_focused_loop_migration_tick_makes_no_branching_calls(
    run_loop_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = run_loop_env
    live_dir = tmp_path / "live-migrations"
    live_dir.mkdir()
    _seed_live_manifest(live_dir)

    monkeypatch.setattr(
        "continuous_refactoring.loop._resolve_live_migrations_dir",
        lambda _repo_root: live_dir,
    )
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)
    monkeypatch.setattr(
        "continuous_refactoring.routing_pipeline.check_phase_ready",
        lambda *_args, **_kwargs: ("yes", "yes"),
    )

    def fake_execute_phase(
        phase, manifest, taste, repo_root, live_dir, artifacts, **_kwargs,
    ):  # type: ignore[no-untyped-def]
        from dataclasses import replace
        from continuous_refactoring.migrations import migration_root
        from continuous_refactoring.phases import ExecutePhaseOutcome

        phase_index = next(
            index
            for index, manifest_phase in enumerate(manifest.phases)
            if manifest_phase.name == phase.name
        )
        updated_phases = tuple(
            replace(p, done=True) if i == phase_index else p
            for i, p in enumerate(manifest.phases)
        )
        updated = replace(
            manifest,
            phases=updated_phases,
            current_phase="",
            status="done",
        )
        save_manifest(
            updated, migration_root(live_dir, manifest.name) / "manifest.json",
        )
        return ExecutePhaseOutcome(status="done", reason="ok")

    monkeypatch.setattr(
        "continuous_refactoring.routing_pipeline.execute_phase", fake_execute_phase,
    )

    captured = _install_argv_spy(monkeypatch)

    exit_code = continuous_refactoring.run_migrations_focused_loop(
        make_run_loop_args(
            repo_root,
            focus_on_live_migrations=True,
            max_consecutive_failures=2,
        )
    )

    assert exit_code == 0
    _assert_no_branching(captured)
