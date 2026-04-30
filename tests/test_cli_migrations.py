from __future__ import annotations

import argparse
import json
import shlex
from dataclasses import replace
from pathlib import Path

import pytest

from conftest import init_repo
from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.artifacts import CommandCapture
from continuous_refactoring.cli import build_parser
from continuous_refactoring.config import register_project, set_live_migrations_dir
from continuous_refactoring.git import run_command
from continuous_refactoring.migration_cli import (
    handle_migration,
    handle_migration_doctor,
    handle_migration_list,
    handle_migration_refine,
    handle_migration_review,
    resolve_migration_target,
)
from continuous_refactoring.migrations import (
    MigrationManifest,
    PhaseSpec,
    load_manifest,
    save_manifest,
)
from continuous_refactoring.planning_publish import snapshot_tree_digest
from continuous_refactoring.planning_state import (
    complete_planning_step,
    load_planning_state,
    new_planning_state,
    planning_stage_stdout_path,
    planning_state_path,
    save_planning_state,
)

_CREATED = "2025-01-01T00:00:00+00:00"
_PHASE = PhaseSpec(
    name="setup",
    file="phase-1-setup.md",
    done=False,
    precondition="always",
)


def test_migration_parser_accepts_list_and_doctor() -> None:
    parser = build_parser()

    list_args = parser.parse_args(["migration", "list"])
    assert list_args.command == "migration"
    assert list_args.migration_command == "list"
    assert list_args.handler.__name__ == "handle_migration"

    filtered = parser.parse_args(
        ["migration", "list", "--status", "planning", "--awaiting-review"]
    )
    assert filtered.status == "planning"
    assert filtered.awaiting_review is True

    doctor_args = parser.parse_args(["migration", "doctor", "my-mig"])
    assert doctor_args.migration_command == "doctor"
    assert doctor_args.target == "my-mig"
    assert doctor_args.all is False

    review_args = parser.parse_args(
        [
            "migration",
            "review",
            "my-mig",
            "--with",
            "codex",
            "--model",
            "test-model",
            "--effort",
            "low",
        ]
    )
    assert review_args.migration_command == "review"
    assert review_args.target == "my-mig"
    assert review_args.agent == "codex"
    assert review_args.model == "test-model"
    assert review_args.effort == "low"


def test_migration_parser_accepts_doctor_all() -> None:
    parser = build_parser()

    args = parser.parse_args(["migration", "doctor", "--all"])

    assert args.command == "migration"
    assert args.migration_command == "doctor"
    assert args.target is None
    assert args.all is True


def test_documented_migration_commands_match_parser() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    parser = build_parser()
    documented_commands = _canonical_migration_commands(readme)

    assert documented_commands == (
        "continuous-refactoring migration list",
        "continuous-refactoring migration list --status planning",
        "continuous-refactoring migration list --awaiting-review",
        "continuous-refactoring migration doctor <slug-or-path>",
        "continuous-refactoring migration doctor --all",
        (
            "continuous-refactoring migration review <slug-or-path> --with codex "
            "--model gpt-5 --effort high"
        ),
        (
            "continuous-refactoring migration refine <slug-or-path> --message "
            "\"split the risky phase\" --with codex --model gpt-5 --effort high"
        ),
        (
            "continuous-refactoring migration refine <slug-or-path> --file "
            "feedback.md --with codex --model gpt-5 --effort high"
        ),
    )

    for command in documented_commands:
        argv = _argv_from_documented_command(command)
        args = parser.parse_args(argv)
        assert args.command == "migration"
        assert args.handler.__name__ == "handle_migration"


def _canonical_migration_commands(readme: str) -> tuple[str, ...]:
    marker = "Canonical migration commands:"
    lines = readme.splitlines()
    start = lines.index(marker)
    block_start = lines.index("```bash", start)
    block_end = lines.index("```", block_start + 1)
    return tuple(
        line
        for line in lines[block_start + 1:block_end]
        if line.startswith("continuous-refactoring migration ")
    )


def _argv_from_documented_command(command: str) -> list[str]:
    parts = shlex.split(command)
    if parts[0] != "continuous-refactoring":
        raise AssertionError(f"unexpected command prefix: {command}")
    return [
        "auth-cleanup" if part == "<slug-or-path>" else part
        for part in parts[1:]
    ]


def test_migration_refine_requires_message_or_file() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as missing_exit:
        parser.parse_args(
            [
                "migration",
                "refine",
                "my-mig",
                "--with",
                "codex",
                "--model",
                "test-model",
                "--effort",
                "low",
            ]
        )
    assert missing_exit.value.code == 2

    with pytest.raises(SystemExit) as both_exit:
        parser.parse_args(
            [
                "migration",
                "refine",
                "my-mig",
                "--message",
                "tighten it",
                "--file",
                "feedback.md",
                "--with",
                "codex",
                "--model",
                "test-model",
                "--effort",
                "low",
            ]
        )
    assert both_exit.value.code == 2

    args = parser.parse_args(
        [
            "migration",
            "refine",
            "my-mig",
            "--message",
            "tighten it",
            "--with",
            "codex",
            "--model",
            "test-model",
            "--effort",
            "low",
        ]
    )

    assert args.migration_command == "refine"
    assert args.target == "my-mig"
    assert args.message == "tighten it"
    assert args.file is None
    assert args.agent == "codex"
    assert args.model == "test-model"
    assert args.effort == "low"


def test_migration_list_includes_planning_ready_review_and_done_statuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    _write_migration(live_dir, "done-mig", status="done", current_phase="")
    planning_dir = _write_migration(
        live_dir, "planning-mig", status="planning", current_phase="", phases=(),
    )
    _write_planning_state(repo, planning_dir)
    _write_migration(
        live_dir,
        "ready-review",
        awaiting_human_review=True,
        human_review_reason="needs approval",
    )

    handle_migration_list(_list_args())

    lines = [line.split("\t") for line in capsys.readouterr().out.splitlines()]
    assert lines == [
        [
            "done-mig",
            "done",
            "(none)",
            "no",
            _CREATED,
            "(none)",
            "(none)",
        ],
        [
            "planning-mig",
            "planning",
            "planning:approaches",
            "no",
            _CREATED,
            "(none)",
            "(none)",
        ],
        [
            "ready-review",
            "ready",
            "phase-1-setup.md",
            "yes",
            _CREATED,
            "(none)",
            "needs approval",
        ],
    ]


def test_migration_list_filters_by_status_and_awaiting_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    _write_migration(
        live_dir, "planning-review", status="planning", current_phase="", phases=(),
    )
    _write_migration(live_dir, "ready-review", awaiting_human_review=True)
    _write_migration(live_dir, "ready-normal")

    handle_migration_list(_list_args(status="ready", awaiting_review=True))

    assert capsys.readouterr().out.splitlines() == [
        "ready-review\tready\tphase-1-setup.md\tyes\t"
        f"{_CREATED}\t(none)\t(none)"
    ]


def test_migration_list_marks_invalid_planning_state_as_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    planning_dir = _write_migration(
        live_dir, "planning-mig", status="planning", current_phase="", phases=(),
    )
    state_path = planning_state_path(planning_dir)
    state_path.parent.mkdir(parents=True)
    state_path.write_text("{not json\n", encoding="utf-8")

    handle_migration_list(_list_args())

    fields = capsys.readouterr().out.strip().split("\t")
    assert fields[0:3] == ["planning-mig", "planning", "planning:blocked"]
    assert fields[-1] == "planning-state-invalid"


def test_migration_list_marks_invalid_ready_cursor_as_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    _write_migration(live_dir, "ready-mig")

    def fail_resolve(_manifest: MigrationManifest) -> PhaseSpec:
        raise ContinuousRefactorError("invalid current phase")

    monkeypatch.setattr(
        "continuous_refactoring.migration_cli.resolve_current_phase",
        fail_resolve,
    )

    handle_migration_list(_list_args())

    fields = capsys.readouterr().out.strip().split("\t")
    assert fields[0:3] == ["ready-mig", "ready", "blocked"]
    assert fields[-1] == "invalid-current-phase"


def test_migration_resolver_accepts_slug_or_path_inside_live_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    migration_dir = _write_migration(live_dir, "target")

    by_slug = resolve_migration_target(
        live_dir=live_dir, repo_root=repo, value="target",
    )
    by_path = resolve_migration_target(
        live_dir=live_dir, repo_root=repo, value="migrations/target",
    )

    assert by_slug.slug == "target"
    assert by_slug.path == migration_dir
    assert by_path == by_slug


def test_migration_resolver_rejects_outside_path_and_symlink_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()

    with pytest.raises(ContinuousRefactorError, match="inside live migrations dir"):
        resolve_migration_target(
            live_dir=live_dir, repo_root=repo, value=str(outside),
        )

    link = live_dir / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"directory symlinks unavailable: {error}")

    with pytest.raises(ContinuousRefactorError, match="symlink"):
        resolve_migration_target(
            live_dir=live_dir, repo_root=repo, value=str(link),
        )


def test_migration_resolver_rejects_parent_traversal_before_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    _write_migration(live_dir, "target")

    with pytest.raises(ContinuousRefactorError, match="parent traversal"):
        resolve_migration_target(
            live_dir=live_dir,
            repo_root=repo,
            value="migrations/../migrations/target",
        )


def test_migration_resolver_rejects_ambiguous_slug_path_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    _write_migration(live_dir, "ambiguous")
    other = _write_migration(live_dir, "other")
    link = repo / "ambiguous"
    try:
        link.symlink_to(other, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"directory symlinks unavailable: {error}")

    with pytest.raises(ContinuousRefactorError, match="ambiguous"):
        resolve_migration_target(
            live_dir=live_dir, repo_root=repo, value="ambiguous",
        )


def test_migration_review_accepts_slug_or_path_inside_live_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    migration_dir = _write_migration(
        live_dir,
        "target",
        awaiting_human_review=True,
    )
    seen: list[Path] = []

    def fake_review(request: object) -> None:
        seen.append(request.target.path)

    monkeypatch.setattr(
        "continuous_refactoring.review_cli.handle_staged_migration_review",
        fake_review,
    )

    handle_migration_review(_review_args("target"))
    handle_migration_review(_review_args("migrations/target"))

    assert seen == [migration_dir, migration_dir]


def test_migration_review_rejects_outside_path_and_symlink_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()

    with pytest.raises(SystemExit) as outside_exit:
        handle_migration_review(_review_args(str(outside)))

    assert outside_exit.value.code == 2
    assert "inside live migrations dir" in capsys.readouterr().err

    link = live_dir / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"directory symlinks unavailable: {error}")

    with pytest.raises(SystemExit) as link_exit:
        handle_migration_review(_review_args(str(link.relative_to(repo))))

    assert link_exit.value.code == 2
    assert "symlink" in capsys.readouterr().err


def test_migration_review_rejects_missing_or_not_flagged_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    _write_migration(live_dir, "not-flagged")

    with pytest.raises(SystemExit) as missing_exit:
        handle_migration_review(_review_args("missing"))

    assert missing_exit.value.code == 2
    assert "does not exist" in capsys.readouterr().err

    with pytest.raises(SystemExit) as not_flagged_exit:
        handle_migration_review(_review_args("not-flagged"))

    assert not_flagged_exit.value.code == 2
    assert "not flagged" in capsys.readouterr().err


def test_migration_review_runs_agent_against_work_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    migration_dir = _write_migration(
        live_dir,
        "target",
        awaiting_human_review=True,
        human_review_reason="needs approval",
    )
    _commit_all(repo)
    seen: dict[str, Path | str] = {}

    def fake_interactive(
        agent: str, model: str, effort: str, prompt: str, repo_root: Path,
    ) -> int:
        seen["agent"] = agent
        seen["cwd"] = repo_root
        seen["prompt"] = prompt
        manifest = load_manifest(repo_root / "manifest.json")
        save_manifest(
            replace(
                manifest,
                awaiting_human_review=False,
                human_review_reason=None,
            ),
            repo_root / "manifest.json",
        )
        return 0

    monkeypatch.setattr(
        "continuous_refactoring.review_cli.run_agent_interactive",
        fake_interactive,
    )

    handle_migration_review(_review_args("target"))

    assert seen["agent"] == "codex"
    assert seen["cwd"] != migration_dir
    assert isinstance(seen["cwd"], Path)
    assert seen["cwd"].name == "target"
    assert str(seen["cwd"]).endswith("/work/target")
    assert str(migration_dir) in str(seen["prompt"])
    assert str(seen["cwd"]) in str(seen["prompt"])
    reloaded = load_manifest(migration_dir / "manifest.json")
    assert reloaded.awaiting_human_review is False
    assert reloaded.human_review_reason is None


def test_migration_review_failure_leaves_live_snapshot_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    migration_dir = _write_migration(
        live_dir,
        "target",
        awaiting_human_review=True,
        human_review_reason="needs approval",
    )
    _commit_all(repo)
    before = snapshot_tree_digest(migration_dir)

    monkeypatch.setattr(
        "continuous_refactoring.review_cli.run_agent_interactive",
        lambda *_args: 7,
    )

    with pytest.raises(SystemExit) as exc_info:
        handle_migration_review(_review_args("target"))

    assert exc_info.value.code == 7
    assert snapshot_tree_digest(migration_dir) == before


def test_migration_review_rejects_stale_base_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    migration_dir = _write_migration(
        live_dir,
        "target",
        awaiting_human_review=True,
        human_review_reason="needs approval",
    )
    _commit_all(repo)
    before = snapshot_tree_digest(migration_dir)
    concurrent: dict[str, str] = {}

    def fake_interactive(
        agent: str, model: str, effort: str, prompt: str, repo_root: Path,
    ) -> int:
        manifest = load_manifest(repo_root / "manifest.json")
        save_manifest(
            replace(
                manifest,
                awaiting_human_review=False,
                human_review_reason=None,
            ),
            repo_root / "manifest.json",
        )
        (migration_dir / "plan.md").write_text("# Changed live plan\n", encoding="utf-8")
        _commit_all(repo, "stale live migration")
        concurrent["digest"] = snapshot_tree_digest(migration_dir)
        concurrent["plan"] = (migration_dir / "plan.md").read_text(encoding="utf-8")
        return 0

    monkeypatch.setattr(
        "continuous_refactoring.review_cli.run_agent_interactive",
        fake_interactive,
    )

    with pytest.raises(SystemExit) as exc_info:
        handle_migration_review(_review_args("target"))

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "stale base snapshot" in err
    assert "continuous-refactoring migration doctor target" in err
    assert "continuous-refactoring migration review target" in err
    assert snapshot_tree_digest(migration_dir) != before
    assert snapshot_tree_digest(migration_dir) == concurrent["digest"]
    assert (migration_dir / "plan.md").read_text(encoding="utf-8") == concurrent["plan"]


def test_migration_review_rejects_inconsistent_workspace_and_preserves_live_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    migration_dir = _write_migration(
        live_dir,
        "target",
        awaiting_human_review=True,
        human_review_reason="needs approval",
    )
    _commit_all(repo)
    before = snapshot_tree_digest(migration_dir)
    before_manifest = load_manifest(migration_dir / "manifest.json")
    before_phase = (migration_dir / _PHASE.file).read_text(encoding="utf-8")

    def fake_interactive(
        agent: str, model: str, effort: str, prompt: str, repo_root: Path,
    ) -> int:
        manifest = load_manifest(repo_root / "manifest.json")
        save_manifest(
            replace(
                manifest,
                awaiting_human_review=False,
                human_review_reason=None,
            ),
            repo_root / "manifest.json",
        )
        (repo_root / _PHASE.file).write_text(
            "# Phase\n\n"
            "## Precondition\n\n"
            "Ready.\n",
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(
        "continuous_refactoring.review_cli.run_agent_interactive",
        fake_interactive,
    )

    with pytest.raises(SystemExit) as exc_info:
        handle_migration_review(_review_args("target"))

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "review workspace validation failed" in err
    assert "missing-phase-definition-of-done" in err
    assert snapshot_tree_digest(migration_dir) == before
    assert load_manifest(migration_dir / "manifest.json") == before_manifest
    assert (migration_dir / _PHASE.file).read_text(encoding="utf-8") == before_phase


def test_migration_review_refuses_publish_when_review_flag_remains(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    migration_dir = _write_migration(
        live_dir,
        "target",
        awaiting_human_review=True,
        human_review_reason="needs approval",
    )
    _commit_all(repo)
    before = snapshot_tree_digest(migration_dir)

    monkeypatch.setattr(
        "continuous_refactoring.review_cli.run_agent_interactive",
        lambda *_args: 0,
    )

    with pytest.raises(SystemExit) as exc_info:
        handle_migration_review(_review_args("target"))

    assert exc_info.value.code == 1
    assert "awaiting_human_review is still set" in capsys.readouterr().err
    assert snapshot_tree_digest(migration_dir) == before


def test_migration_refine_rejects_outside_path_and_symlink_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()

    with pytest.raises(SystemExit) as outside_exit:
        handle_migration_refine(_refine_args(str(outside)))

    assert outside_exit.value.code == 2
    assert "inside live migrations dir" in capsys.readouterr().err

    link = live_dir / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"directory symlinks unavailable: {error}")

    with pytest.raises(SystemExit) as link_exit:
        handle_migration_refine(_refine_args(str(link.relative_to(repo))))

    assert link_exit.value.code == 2
    assert "symlink" in capsys.readouterr().err


def test_migration_refine_resumes_from_current_planning_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    migration_dir = _write_migration(
        live_dir, "target", status="planning", current_phase="", phases=(),
    )
    _write_completed_planning_state(
        repo,
        migration_dir,
        [
            ("approaches", "completed", "Generated approaches.\n"),
            ("pick-best", "completed", "Chose incremental.\n"),
        ],
    )
    _commit_all(repo)
    fake = _RefineAgent(
        [
            _agent_response(
                "Expanded.\n",
                {
                    "plan.md": "# Refined Plan\n",
                    _PHASE.file: _phase_doc("always", "Done."),
                },
            )
        ]
    )
    monkeypatch.setattr("continuous_refactoring.planning.maybe_run_agent", fake)

    handle_migration_refine(_refine_args("target", message="split phase one"))

    state = load_planning_state(repo, planning_state_path(migration_dir))
    assert fake.stage_labels == ["expand"]
    assert state.next_step == "review"
    assert state.feedback[-1].source == "message"
    assert state.feedback[-1].text == "split phase one"
    assert (migration_dir / "plan.md").read_text(encoding="utf-8") == "# Refined Plan\n"


def test_migration_refine_reopens_unexecuted_ready_migration_to_planning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    migration_dir = _write_migration(live_dir, "target")
    _write_terminal_ready_planning_state(repo, migration_dir)
    _commit_all(repo)
    fake = _RefineAgent(
        [
            _agent_response(
                "Revised.\n",
                {
                    "plan.md": "# Plan v2\n",
                    _PHASE.file: _phase_doc("always", "Still done."),
                },
            )
        ]
    )
    monkeypatch.setattr("continuous_refactoring.planning.maybe_run_agent", fake)

    handle_migration_refine(_refine_args("target", message="make setup smaller"))

    manifest = load_manifest(migration_dir / "manifest.json")
    state = load_planning_state(repo, planning_state_path(migration_dir))
    assert fake.stage_labels == ["revise"]
    assert manifest.status == "planning"
    assert manifest.awaiting_human_review is False
    assert manifest.human_review_reason is None
    assert manifest.current_phase == "setup"
    assert all(not phase.done for phase in manifest.phases)
    assert state.next_step == "review-2"
    assert state.revision_base_step_count == 5
    assert planning_stage_stdout_path(migration_dir, "final-review").is_file()


def test_migration_refine_refuses_migration_with_completed_phase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    done_phase = replace(_PHASE, done=True)
    migration_dir = _write_migration(live_dir, "target", phases=(done_phase,))
    _write_terminal_ready_planning_state(repo, migration_dir)
    _commit_all(repo)
    before = snapshot_tree_digest(migration_dir)

    with pytest.raises(SystemExit) as exc_info:
        handle_migration_refine(_refine_args("target"))

    assert exc_info.value.code == 2
    assert "completed phase" in capsys.readouterr().err
    assert snapshot_tree_digest(migration_dir) == before


def test_migration_refine_refuses_non_reopenable_ready_planning_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    migration_dir = _write_migration(live_dir, "target")
    _write_terminal_skipped_planning_state(repo, migration_dir)
    _commit_all(repo)
    before = snapshot_tree_digest(migration_dir)

    with pytest.raises(SystemExit) as exc_info:
        handle_migration_refine(_refine_args("target"))

    assert exc_info.value.code == 2
    assert "Cannot reopen planning state" in capsys.readouterr().err
    assert snapshot_tree_digest(migration_dir) == before


def test_migration_refine_failure_leaves_live_snapshot_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    migration_dir = _write_migration(
        live_dir, "target", status="planning", current_phase="", phases=(),
    )
    _write_planning_state(repo, migration_dir)
    _commit_all(repo)
    before = snapshot_tree_digest(migration_dir)
    before_state = planning_state_path(migration_dir).read_text(encoding="utf-8")
    fake = _RefineAgent([_agent_response("partial\n", {}, returncode=1)])
    monkeypatch.setattr("continuous_refactoring.planning.maybe_run_agent", fake)

    with pytest.raises(SystemExit) as exc_info:
        handle_migration_refine(_refine_args("target", message="try it"))

    assert exc_info.value.code == 1
    assert snapshot_tree_digest(migration_dir) == before
    assert planning_state_path(migration_dir).read_text(encoding="utf-8") == before_state


def test_migration_refine_rejects_stale_base_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    migration_dir = _write_migration(
        live_dir, "target", status="planning", current_phase="", phases=(),
    )
    _write_planning_state(repo, migration_dir)
    _commit_all(repo)
    concurrent: dict[str, str] = {}

    def on_call(_migration_dir: Path) -> None:
        (migration_dir / "plan.md").write_text("# Concurrent Plan\n", encoding="utf-8")
        _commit_all(repo, "stale live migration")
        concurrent["digest"] = snapshot_tree_digest(migration_dir)
        concurrent["plan"] = (migration_dir / "plan.md").read_text(encoding="utf-8")

    fake = _RefineAgent([_agent_response("Approaches.\n", {})], on_call=on_call)
    monkeypatch.setattr("continuous_refactoring.planning.maybe_run_agent", fake)

    with pytest.raises(SystemExit) as exc_info:
        handle_migration_refine(_refine_args("target", message="try it"))

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "stale base snapshot" in err
    assert "continuous-refactoring migration doctor target" in err
    assert "continuous-refactoring migration refine target" in err
    assert snapshot_tree_digest(migration_dir) == concurrent["digest"]
    assert (migration_dir / "plan.md").read_text(encoding="utf-8") == concurrent["plan"]


def test_migration_doctor_checks_one_migration_by_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    _write_migration(live_dir, "valid")

    handle_migration_doctor(_doctor_args(target="valid"))

    assert capsys.readouterr().out == ""


def test_migration_doctor_all_checks_every_live_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    _write_migration(live_dir, "valid")
    (live_dir / "broken").mkdir()

    with pytest.raises(SystemExit) as exc_info:
        handle_migration_doctor(_doctor_args(all_=True))

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "broken\terror\tmissing-manifest" in out


def test_migration_doctor_reports_missing_planning_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    _write_migration(
        live_dir, "planning-mig", status="planning", current_phase="", phases=(),
    )

    with pytest.raises(SystemExit) as exc_info:
        handle_migration_doctor(_doctor_args(target="planning-mig"))

    assert exc_info.value.code == 1
    assert "planning-mig\terror\tplanning-state-missing" in capsys.readouterr().out


def test_migration_doctor_reports_ready_gate_phase_doc_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    migration_dir = _write_migration(live_dir, "ready-mig")
    (migration_dir / _PHASE.file).write_text(
        "# Phase\n\n## Precondition\n\nReady.\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc_info:
        handle_migration_doctor(_doctor_args(target="ready-mig"))

    assert exc_info.value.code == 1
    assert "ready-mig\terror\tmissing-phase-definition-of-done" in (
        capsys.readouterr().out
    )


def test_migration_doctor_reports_transaction_root_and_lock_presence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    tx_root = live_dir / "__transactions__"
    (tx_root / "tx-leftover").mkdir(parents=True)
    lock = tx_root / ".lock"
    lock.mkdir()
    (lock / "owner.json").write_text(
        json.dumps(
            {
                "pid": 123,
                "operation": "planning-publish",
                "created_at": _CREATED,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc_info:
        handle_migration_doctor(_doctor_args(all_=True))

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "__transactions__\terror\tpublish-lock-present" in out
    assert "pid=123" in out
    assert "__transactions__\terror\ttransaction-leftover" in out


def test_migration_doctor_reports_invalid_transaction_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    (live_dir / "__transactions__").write_text("not a dir\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        handle_migration_doctor(_doctor_args(all_=True))

    assert exc_info.value.code == 1
    assert "__transactions__\terror\ttransaction-root-invalid" in (
        capsys.readouterr().out
    )


def test_migration_doctor_exits_nonzero_on_error_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _repo, live_dir = _init_migration_project(tmp_path, monkeypatch)
    _write_migration(live_dir, "missing-plan", write_plan=False)

    with pytest.raises(SystemExit) as exc_info:
        handle_migration_doctor(_doctor_args(target="missing-plan"))

    assert exc_info.value.code == 1
    assert "missing-plan\terror\tmissing-plan" in capsys.readouterr().out


def test_migration_dispatches_subcommands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        "continuous_refactoring.migration_cli.handle_migration_list",
        lambda _args: seen.append("list"),
    )
    monkeypatch.setattr(
        "continuous_refactoring.migration_cli.handle_migration_doctor",
        lambda _args: seen.append("doctor"),
    )
    monkeypatch.setattr(
        "continuous_refactoring.migration_cli.handle_migration_review",
        lambda _args: seen.append("review"),
    )
    monkeypatch.setattr(
        "continuous_refactoring.migration_cli.handle_migration_refine",
        lambda _args: seen.append("refine"),
    )

    handle_migration(argparse.Namespace(migration_command="list"))
    handle_migration(argparse.Namespace(migration_command="doctor"))
    handle_migration(argparse.Namespace(migration_command="review"))
    handle_migration(argparse.Namespace(migration_command="refine"))

    assert seen == ["list", "doctor", "review", "refine"]


def test_migration_exits_2_without_subcommand(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        handle_migration(argparse.Namespace(migration_command=None))

    assert exc_info.value.code == 2
    assert "Usage: continuous-refactoring migration" in capsys.readouterr().err


def _init_migration_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    init_repo(repo)
    monkeypatch.chdir(repo)
    project = register_project(repo)
    live_dir = repo / "migrations"
    live_dir.mkdir()
    set_live_migrations_dir(project.entry.uuid, "migrations")
    return repo, live_dir


def _write_migration(
    live_dir: Path,
    slug: str,
    *,
    status: str = "ready",
    awaiting_human_review: bool = False,
    current_phase: str = "setup",
    human_review_reason: str | None = None,
    phases: tuple[PhaseSpec, ...] = (_PHASE,),
    write_plan: bool = True,
    write_phase: bool = True,
) -> Path:
    migration_dir = live_dir / slug
    migration_dir.mkdir(parents=True)
    if write_plan:
        (migration_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")
    if write_phase:
        for phase in phases:
            (migration_dir / phase.file).write_text(
                "# Phase\n\n"
                "## Precondition\n\n"
                "Ready.\n\n"
                "## Definition of Done\n\n"
                "Done.\n",
                encoding="utf-8",
            )
    save_manifest(
        MigrationManifest(
            name=slug,
            created_at=_CREATED,
            last_touch=_CREATED,
            wake_up_on=None,
            awaiting_human_review=awaiting_human_review,
            status=status,
            current_phase=current_phase,
            phases=phases,
            human_review_reason=human_review_reason,
        ),
        migration_dir / "manifest.json",
    )
    return migration_dir


def _write_planning_state(repo: Path, migration_dir: Path) -> None:
    save_planning_state(
        new_planning_state("src/example.py", now=_CREATED),
        planning_state_path(migration_dir),
        repo_root=repo,
        published_migration_root=migration_dir,
    )


def _write_completed_planning_state(
    repo: Path,
    migration_dir: Path,
    completed: list[tuple[str, str, str]],
) -> None:
    state = new_planning_state("src/example.py", now=_CREATED)
    for step, outcome, stdout in completed:
        stdout_path = planning_stage_stdout_path(migration_dir, step)
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text(stdout, encoding="utf-8")
        state = complete_planning_step(
            state,
            step,
            outcome,
            {"stdout": stdout_path.relative_to(repo).as_posix()},
            completed_at=_CREATED,
            final_reason="ready" if step == "final-review" else None,
        )
    save_planning_state(
        state,
        planning_state_path(migration_dir),
        repo_root=repo,
        published_migration_root=migration_dir,
    )


def _write_terminal_ready_planning_state(repo: Path, migration_dir: Path) -> None:
    _write_completed_planning_state(
        repo,
        migration_dir,
        [
            ("approaches", "completed", "Generated approaches.\n"),
            ("pick-best", "completed", "Chose incremental.\n"),
            ("expand", "completed", "Expanded.\n"),
            ("review", "clear", "No findings.\n"),
            ("final-review", "approve-auto", "final-decision: approve-auto - ready\n"),
        ],
    )


def _write_terminal_skipped_planning_state(repo: Path, migration_dir: Path) -> None:
    _write_completed_planning_state(
        repo,
        migration_dir,
        [
            ("approaches", "completed", "Generated approaches.\n"),
            ("pick-best", "completed", "Chose incremental.\n"),
            ("expand", "completed", "Expanded.\n"),
            ("review", "clear", "No findings.\n"),
            ("final-review", "reject", "final-decision: reject - flawed\n"),
        ],
    )


def _commit_all(repo: Path, message: str = "test state") -> None:
    run_command(["git", "add", "-A"], cwd=repo)
    run_command(["git", "commit", "-m", message], cwd=repo)


def _list_args(
    *,
    status: str | None = None,
    awaiting_review: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(status=status, awaiting_review=awaiting_review)


def _doctor_args(
    *,
    target: str | None = None,
    all_: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(target=target, all=all_)


def _review_args(target: str) -> argparse.Namespace:
    return argparse.Namespace(
        target=target,
        agent="codex",
        model="test-model",
        effort="low",
    )


def _refine_args(
    target: str,
    *,
    message: str = "please refine this migration",
    file: Path | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        target=target,
        message=message if file is None else None,
        file=file,
        agent="codex",
        model="test-model",
        effort="low",
    )


def _phase_doc(precondition: str, definition_of_done: str) -> str:
    return (
        f"# Phase\n\n"
        f"## Precondition\n\n{precondition}\n\n"
        f"## Definition of Done\n\n{definition_of_done}\n"
    )


def _agent_response(
    stdout: str,
    writes: dict[str, str] | None = None,
    *,
    returncode: int = 0,
) -> tuple[str, dict[str, str], int]:
    return stdout, writes or {}, returncode


class _RefineAgent:
    def __init__(
        self,
        responses: list[tuple[str, dict[str, str], int]],
        *,
        on_call: object | None = None,
    ) -> None:
        self._responses = responses
        self._index = 0
        self._on_call = on_call
        self.stage_labels: list[str] = []
        self.prompts: list[str] = []

    def __call__(self, **kwargs: object) -> CommandCapture:
        assert self._index < len(self._responses)
        stdout, writes, returncode = self._responses[self._index]
        self._index += 1
        prompt = str(kwargs["prompt"])
        stdout_path = Path(str(kwargs["stdout_path"]))
        stderr_path = Path(str(kwargs["stderr_path"]))
        migration_dir = _prompt_migration_dir(prompt)

        self.prompts.append(prompt)
        self.stage_labels.append(stdout_path.parent.name)
        for rel_path, content in writes.items():
            path = migration_dir / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        if self._on_call is not None:
            self._on_call(migration_dir)

        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.write_text("", encoding="utf-8")
        return CommandCapture(
            command=("fake",),
            returncode=returncode,
            stdout=stdout,
            stderr="",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )


def _prompt_migration_dir(prompt: str) -> Path:
    for line in prompt.splitlines():
        if line.startswith("Migration directory:"):
            return Path(line.split(":", 1)[1].strip())
    raise AssertionError("Migration directory missing from prompt")
