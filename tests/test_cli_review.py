from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest

from continuous_refactoring.cli import build_parser
from continuous_refactoring.config import register_project, set_live_migrations_dir
from continuous_refactoring.migrations import (
    MigrationManifest,
    PhaseSpec,
    load_manifest as load_migration_manifest,
    save_manifest as save_migration,
)
from continuous_refactoring.review_cli import (
    handle_review,
    handle_review_list,
    handle_review_perform,
)

_PHASES = (
    PhaseSpec(name="setup", file="phase-1-setup.md", done=True, precondition="always"),
    PhaseSpec(
        name="review-target",
        file="phase-2-review-target.md",
        done=False,
        precondition="setup complete",
    ),
)


def test_review_parser_accepts_list_and_perform_subcommands() -> None:
    parser = build_parser()

    review_args = parser.parse_args(["review"])
    assert review_args.command == "review"
    assert review_args.review_command is None

    list_args = parser.parse_args(["review", "list"])
    assert list_args.command == "review"
    assert list_args.review_command == "list"

    perform_args = parser.parse_args(
        [
            "review",
            "perform",
            "my-mig",
            "--with",
            "codex",
            "--model",
            "test-model",
            "--effort",
            "low",
        ],
    )
    assert perform_args.command == "review"
    assert perform_args.review_command == "perform"
    assert perform_args.migration == "my-mig"
    assert perform_args.agent == "codex"
    assert perform_args.model == "test-model"
    assert perform_args.effort == "low"


def test_parser_binds_handlers_for_top_level_commands() -> None:
    parser = build_parser()

    assert parser.parse_args(["init"]).handler.__name__ == "_handle_init"
    assert parser.parse_args(["taste"]).handler.__name__ == "_handle_taste"
    assert parser.parse_args(["upgrade"]).handler.__name__ == "_handle_upgrade"
    assert parser.parse_args(["review"]).handler.__name__ == "handle_review"
    assert parser.parse_args(
        ["run-once", "--with", "codex", "--model", "m", "--scope-instruction", "s"]
    ).handler.__name__ == "_handle_run_once"
    assert parser.parse_args(
        [
            "run",
            "--with",
            "codex",
            "--model",
            "m",
            "--scope-instruction",
            "s",
            "--max-refactors",
            "1",
        ]
    ).handler.__name__ == "_handle_run"


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=path, check=True, capture_output=True,
    )
    (path / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "README.md"], cwd=path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True,
    )


def _make_perform_args(migration: str) -> argparse.Namespace:
    return argparse.Namespace(
        migration=migration,
        agent="codex",
        model="test-model",
        effort="low",
    )


def _commit_all(repo: Path, message: str = "test state") -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True)


def _init_review_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)
    monkeypatch.chdir(repo)

    project = register_project(repo)
    live_dir = repo / ".migrations"
    live_dir.mkdir()
    set_live_migrations_dir(project.entry.uuid, ".migrations")
    return repo, live_dir


def _init_unconfigured_review_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "project"
    _init_repo(repo)
    monkeypatch.chdir(repo)
    return repo


def _make_manifest(
    name: str,
    *,
    awaiting_human_review: bool = False,
    status: str = "ready",
    current_phase: str = "review-target",
    last_touch: str = "2025-01-01T00:00:00+00:00",
    human_review_reason: str | None = None,
) -> MigrationManifest:
    return MigrationManifest(
        name=name,
        created_at="2025-01-01T00:00:00+00:00",
        last_touch=last_touch,
        wake_up_on=None,
        awaiting_human_review=awaiting_human_review,
        status=status,
        current_phase=current_phase,
        phases=_PHASES,
        human_review_reason=human_review_reason,
    )


def test_review_list_filters_flagged_migrations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, live_dir = _init_review_project(tmp_path, monkeypatch)

    save_migration(
        _make_manifest(
            "listed-a",
            awaiting_human_review=True,
            status="in-progress",
            current_phase="setup",
            last_touch="2025-03-02T14:00:00+00:00",
        ),
        live_dir / "mig-b" / "manifest.json",
    )
    save_migration(
        _make_manifest(
            "listed-without-phase",
            awaiting_human_review=True,
            status="ready",
            current_phase="",
            last_touch="2025-03-03T16:00:00+00:00",
            human_review_reason="phase cursor cleared",
        ),
        live_dir / "mig-no-phase" / "manifest.json",
    )
    save_migration(
        _make_manifest("mig-c", awaiting_human_review=False, status="done"),
        live_dir / "mig-c" / "manifest.json",
    )
    save_migration(
        _make_manifest(
            "listed-z",
            awaiting_human_review=True,
            status="ready",
            current_phase="review-target",
            last_touch="2025-03-01T12:00:00+00:00",
            human_review_reason="needs security audit",
        ),
        live_dir / "mig-a" / "manifest.json",
    )

    handle_review_list()

    out = capsys.readouterr().out
    lines = [line for line in out.strip().splitlines() if line]
    assert len(lines) == 3

    fields_a = lines[0].split("\t")
    assert fields_a == [
        "listed-z",
        "ready",
        "phase-2-review-target.md",
        "review-target",
        "2025-03-01T12:00:00+00:00",
        "needs security audit",
    ]

    fields_b = lines[1].split("\t")
    assert fields_b == [
        "listed-a",
        "in-progress",
        "phase-1-setup.md",
        "setup",
        "2025-03-02T14:00:00+00:00",
        "(no reason recorded)",
    ]

    fields_no_phase = lines[2].split("\t")
    assert fields_no_phase == [
        "listed-without-phase",
        "ready",
        "(none)",
        "(none)",
        "2025-03-03T16:00:00+00:00",
        "phase cursor cleared",
    ]


def test_review_list_ignores_hidden_and_transaction_dirs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, live_dir = _init_review_project(tmp_path, monkeypatch)
    save_migration(
        _make_manifest(
            "visible-review",
            awaiting_human_review=True,
            human_review_reason="visible",
        ),
        live_dir / "visible-review" / "manifest.json",
    )
    save_migration(
        _make_manifest(
            "hidden-review",
            awaiting_human_review=True,
            human_review_reason="hidden",
        ),
        live_dir / ".hidden-review" / "manifest.json",
    )
    save_migration(
        _make_manifest(
            "transaction-review",
            awaiting_human_review=True,
            human_review_reason="transaction",
        ),
        live_dir / "__transactions__" / "manifest.json",
    )

    handle_review_list()

    out = capsys.readouterr().out
    assert "visible-review\tready" in out
    assert "hidden-review" not in out
    assert "transaction-review" not in out


@pytest.mark.parametrize(
    ("handler", "error_code", "setup", "expected_message"),
    [
        (
            handle_review_list,
            1,
            lambda tmp_path, monkeypatch: _init_unconfigured_review_repo(
                tmp_path, monkeypatch,
            ),
            "project not initialized",
        ),
        (
            lambda: handle_review_perform(_make_perform_args("my-mig")),
            2,
            lambda tmp_path, monkeypatch: _init_unconfigured_review_repo(
                tmp_path, monkeypatch,
            ),
            "project not initialized",
        ),
        (
            handle_review_list,
            1,
            lambda tmp_path, monkeypatch: register_project(
                _init_unconfigured_review_repo(tmp_path, monkeypatch),
            ),
            "live-migrations-dir",
        ),
        (
            lambda: handle_review_perform(_make_perform_args("my-mig")),
            2,
            lambda tmp_path, monkeypatch: register_project(
                _init_unconfigured_review_repo(tmp_path, monkeypatch),
            ),
            "live-migrations-dir",
        ),
        (
            handle_review_list,
            1,
            lambda tmp_path, monkeypatch: _configure_escaped_live_dir(
                _init_unconfigured_review_repo(tmp_path, monkeypatch),
            ),
            "escapes repo",
        ),
        (
            lambda: handle_review_perform(_make_perform_args("my-mig")),
            2,
            lambda tmp_path, monkeypatch: _configure_escaped_live_dir(
                _init_unconfigured_review_repo(tmp_path, monkeypatch),
            ),
            "escapes repo",
        ),
    ],
)
def test_review_commands_surface_shared_context_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    handler: object,
    error_code: int,
    setup: object,
    expected_message: str,
) -> None:
    setup(tmp_path, monkeypatch)

    with pytest.raises(SystemExit) as exc_info:
        handler()

    assert exc_info.value.code == error_code
    err = capsys.readouterr().err
    assert expected_message in err


def _configure_escaped_live_dir(repo: Path) -> None:
    project = register_project(repo)
    set_live_migrations_dir(project.entry.uuid, "../elsewhere")


def _setup_review_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    awaiting: bool = True,
    current_phase: str = "review-target",
    human_review_reason: str | None = None,
) -> tuple[Path, Path]:
    repo, live_dir = _init_review_project(tmp_path, monkeypatch)
    save_migration(
        _make_manifest(
            "my-mig",
            awaiting_human_review=awaiting,
            status="ready",
            current_phase=current_phase,
            human_review_reason=human_review_reason,
        ),
        live_dir / "my-mig" / "manifest.json",
    )
    (live_dir / "my-mig" / "plan.md").write_text("# Plan\n", encoding="utf-8")
    for phase in _PHASES:
        (live_dir / "my-mig" / phase.file).write_text(
            "# Phase\n\n"
            "## Precondition\n\n"
            "Ready.\n\n"
            "## Definition of Done\n\n"
            "Done.\n",
            encoding="utf-8",
        )
    return repo, live_dir


def test_review_perform_happy_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, live_dir = _setup_review_project(
        tmp_path, monkeypatch,
        awaiting=True,
        human_review_reason="needs security audit",
    )
    _commit_all(repo)
    manifest_path = live_dir / "my-mig" / "manifest.json"
    captured_prompt: dict[str, str] = {}

    def fake_interactive(
        agent: str, model: str, effort: str, prompt: str, repo_root: Path,
    ) -> int:
        captured_prompt["prompt"] = prompt
        captured_prompt["repo_root"] = str(repo_root)
        manifest = load_migration_manifest(repo_root / "manifest.json")
        from dataclasses import replace
        updated = replace(
            manifest,
            awaiting_human_review=False,
            human_review_reason=None,
        )
        save_migration(updated, repo_root / "manifest.json")
        return 0

    monkeypatch.setattr(
        "continuous_refactoring.review_cli.run_agent_interactive", fake_interactive,
    )

    handle_review_perform(_make_perform_args("my-mig"))

    assert "needs security audit" in captured_prompt["prompt"]
    assert "phase-2-review-target.md" in captured_prompt["prompt"]
    assert "Name: review-target" in captured_prompt["prompt"]
    assert captured_prompt["repo_root"] != str(Path.cwd().resolve())
    assert captured_prompt["repo_root"].endswith("/work/my-mig")

    reloaded = load_migration_manifest(manifest_path)
    assert reloaded.awaiting_human_review is False
    assert reloaded.human_review_reason is None


def test_review_perform_happy_path_without_current_phase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, live_dir = _setup_review_project(
        tmp_path, monkeypatch,
        awaiting=True,
        current_phase="",
        human_review_reason="phase cursor cleared",
    )
    _commit_all(repo)
    manifest_path = live_dir / "my-mig" / "manifest.json"
    captured_prompt: dict[str, str] = {}

    def fake_interactive(
        agent: str, model: str, effort: str, prompt: str, repo_root: Path,
    ) -> int:
        captured_prompt["prompt"] = prompt
        manifest = load_migration_manifest(repo_root / "manifest.json")
        from dataclasses import replace
        updated = replace(
            manifest,
            awaiting_human_review=False,
            current_phase="review-target",
            human_review_reason=None,
        )
        save_migration(updated, repo_root / "manifest.json")
        return 0

    monkeypatch.setattr(
        "continuous_refactoring.review_cli.run_agent_interactive", fake_interactive,
    )

    handle_review_perform(_make_perform_args("my-mig"))

    assert "phase cursor cleared" in captured_prompt["prompt"]
    assert "Current phase file: (none)" in captured_prompt["prompt"]
    assert "Current phase name: (none)" in captured_prompt["prompt"]


def test_review_perform_exits_1_when_flag_not_cleared(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, live_dir = _setup_review_project(tmp_path, monkeypatch, awaiting=True)
    _commit_all(repo)

    def fake_interactive(
        agent: str, model: str, effort: str, prompt: str, repo_root: Path,
    ) -> int:
        return 0

    monkeypatch.setattr(
        "continuous_refactoring.review_cli.run_agent_interactive", fake_interactive,
    )

    with pytest.raises(SystemExit) as exc_info:
        handle_review_perform(_make_perform_args("my-mig"))

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "not completed" in err


def test_review_perform_exits_with_agent_returncode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, _live_dir = _setup_review_project(tmp_path, monkeypatch, awaiting=True)
    _commit_all(repo)

    def fake_interactive(
        agent: str, model: str, effort: str, prompt: str, repo_root: Path,
    ) -> int:
        return 7

    monkeypatch.setattr(
        "continuous_refactoring.review_cli.run_agent_interactive", fake_interactive,
    )

    with pytest.raises(SystemExit) as exc_info:
        handle_review_perform(_make_perform_args("my-mig"))

    assert exc_info.value.code == 7
    err = capsys.readouterr().err
    assert "review agent exited with code 7" in err


def test_review_perform_exits_2_when_migration_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _init_review_project(tmp_path, monkeypatch)

    with pytest.raises(SystemExit) as exc_info:
        handle_review_perform(_make_perform_args("nonexistent"))

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "does not exist" in err


def test_review_perform_exits_2_when_not_flagged_for_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, live_dir = _setup_review_project(tmp_path, monkeypatch, awaiting=False)

    with pytest.raises(SystemExit) as exc_info:
        handle_review_perform(_make_perform_args("my-mig"))

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "not flagged" in err


def test_top_level_review_perform_routes_to_migration_review_compatibility_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _repo, live_dir = _setup_review_project(
        tmp_path,
        monkeypatch,
        awaiting=True,
        human_review_reason="needs approval",
    )
    seen: dict[str, object] = {}

    def fake_staged_review(request: object) -> None:
        seen["slug"] = request.target.slug
        seen["path"] = request.target.path
        seen["agent"] = request.agent
        seen["model"] = request.model
        seen["effort"] = request.effort

    monkeypatch.setattr(
        "continuous_refactoring.review_cli.handle_staged_migration_review",
        fake_staged_review,
    )

    handle_review_perform(_make_perform_args("my-mig"))

    assert seen == {
        "slug": "my-mig",
        "path": live_dir / "my-mig",
        "agent": "codex",
        "model": "test-model",
        "effort": "low",
    }


def test_review_dispatches_list_subcommand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    monkeypatch.setattr(
        "continuous_refactoring.review_cli.handle_review_list",
        lambda: seen.append("list"),
    )

    handle_review(argparse.Namespace(review_command="list"))

    assert seen == ["list"]


def test_review_dispatches_perform_subcommand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def fake_perform(args: argparse.Namespace) -> None:
        seen.append(args.migration)

    monkeypatch.setattr(
        "continuous_refactoring.review_cli.handle_review_perform",
        fake_perform,
    )

    handle_review(argparse.Namespace(review_command="perform", migration="my-mig"))

    assert seen == ["my-mig"]


def test_review_exits_2_without_subcommand(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        handle_review(argparse.Namespace(review_command=None))

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "Usage: continuous-refactoring review {list,perform}" in err
