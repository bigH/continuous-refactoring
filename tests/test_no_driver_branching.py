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
    install_run_command_spy,
    make_run_loop_args,
    make_run_once_args,
    noop_agent,
    noop_tests,
)


_BRANCH_SWITCH_COMMANDS = {"checkout", "switch"}
_BRANCH_MUTATION_FLAGS = {
    "--copy",
    "--delete",
    "--edit-description",
    "--move",
    "--no-track",
    "--set-upstream-to",
    "--track",
    "--unset-upstream",
    "-C",
    "-D",
    "-M",
    "-c",
    "-d",
    "-m",
    "-u",
}
_BRANCH_MUTATION_FLAG_PREFIXES = ("--set-upstream-to=",)
_READ_ONLY_BRANCH_FLAGS = {
    "--all",
    "--contains",
    "--format",
    "--list",
    "--merged",
    "--no-contains",
    "--no-merged",
    "--points-at",
    "--remotes",
    "--show-current",
    "--sort",
    "-a",
    "-l",
    "-r",
}


def _is_branching_argv(argv: tuple[str, ...]) -> bool:
    if not argv or argv[0] != "git":
        return False
    command = argv[1] if len(argv) > 1 else ""
    args = argv[2:]
    if command in _BRANCH_SWITCH_COMMANDS:
        return True
    if command != "branch":
        return False
    if _has_branch_mutation_flag(args):
        return True
    if _is_read_only_branch_args(args):
        return False
    return any(not arg.startswith("-") for arg in args)


def _has_branch_mutation_flag(args: tuple[str, ...]) -> bool:
    return any(
        arg in _BRANCH_MUTATION_FLAGS
        or any(arg.startswith(prefix) for prefix in _BRANCH_MUTATION_FLAG_PREFIXES)
        for arg in args
    )


def _is_read_only_branch_args(args: tuple[str, ...]) -> bool:
    return not args or args[0] in _READ_ONLY_BRANCH_FLAGS


@pytest.mark.parametrize(
    "argv",
    [
        ("git", "branch", "feature"),
        ("git", "branch", "-c", "main", "feature"),
        ("git", "branch", "-D", "feature"),
        ("git", "branch", "--delete", "feature"),
        ("git", "branch", "--edit-description"),
        ("git", "branch", "--set-upstream-to=origin/main"),
        ("git", "branch", "--unset-upstream"),
        ("git", "checkout", "feature"),
        ("git", "checkout", "-b", "feature"),
        ("git", "switch", "feature"),
    ],
)
def test_branching_detector_flags_branch_mutations(argv: tuple[str, ...]) -> None:
    assert _is_branching_argv(argv)


@pytest.mark.parametrize(
    "argv",
    [
        (),
        ("python", "-m", "pytest"),
        ("git", "status", "--porcelain"),
        ("git", "branch"),
        ("git", "branch", "--show-current"),
        ("git", "branch", "--list"),
        ("git", "branch", "--list", "feature-*"),
        ("git", "branch", "--contains", "HEAD"),
        ("git", "branch", "--merged", "main"),
        ("git", "branch", "--no-contains", "HEAD"),
    ],
)
def test_branching_detector_allows_non_mutating_commands(
    argv: tuple[str, ...],
) -> None:
    assert not _is_branching_argv(argv)


def test_run_arg_helpers_match_cli_effort_defaults(run_once_env: Path) -> None:
    run_once_args = make_run_once_args(run_once_env)
    run_loop_args = make_run_loop_args(run_once_env)

    assert run_once_args.effort == "low"
    assert run_once_args.default_effort == "low"
    assert run_once_args.max_allowed_effort == "xhigh"
    assert run_loop_args.effort == "low"
    assert run_loop_args.default_effort == "low"
    assert run_loop_args.max_allowed_effort == "xhigh"


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
    (migration_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")
    for phase in manifest.phases:
        (migration_dir / phase.file).write_text(f"# {phase.name}\n", encoding="utf-8")
    save_manifest(manifest, migration_dir / "manifest.json")


def test_run_once_makes_no_branching_calls(
    run_once_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("continuous_refactoring.loop.maybe_run_agent", noop_agent)
    monkeypatch.setattr("continuous_refactoring.loop.run_tests", noop_tests)

    captured = install_run_command_spy(monkeypatch)

    exit_code = continuous_refactoring.run_once(make_run_once_args(run_once_env))

    assert exit_code == 0
    assert ("git", "ls-files", "-z") in captured
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

    captured = install_run_command_spy(monkeypatch)

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
        "continuous_refactoring.migration_tick.check_phase_ready",
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
        "continuous_refactoring.migration_tick.execute_phase", fake_execute_phase,
    )

    captured = install_run_command_spy(monkeypatch)

    exit_code = continuous_refactoring.run_migrations_focused_loop(
        make_run_loop_args(
            repo_root,
            focus_on_live_migrations=True,
            max_consecutive_failures=2,
        )
    )

    assert exit_code == 0
    _assert_no_branching(captured)
