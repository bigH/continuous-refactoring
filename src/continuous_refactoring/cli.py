from __future__ import annotations

import argparse
import sys
from pathlib import Path

__all__ = [
    "build_parser",
    "cli_main",
    "parse_max_attempts",
]

from continuous_refactoring.agent import run_agent_interactive
from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.loop import run_loop, run_once


def parse_max_attempts(value: str) -> int:
    try:
        attempts = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    if attempts < 0:
        raise argparse.ArgumentTypeError("--max-attempts must be >= 0")
    return attempts


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--with",
        dest="agent",
        choices=("codex", "claude"),
        required=True,
        help="Which agent backend to use.",
    )
    parser.add_argument("--model", required=True, help="Model name.")
    parser.add_argument("--effort", required=True, help="Effort level.")
    parser.add_argument(
        "--validation-command",
        default="uv run pytest",
        help="Command to validate the repo.",
    )
    parser.add_argument("--extensions", default=None, help="File extensions, e.g. .py,.ts")
    parser.add_argument("--globs", default=None, help="Colon-separated glob patterns.")
    parser.add_argument("--targets", type=Path, default=None, help="JSONL targets file.")
    parser.add_argument("--paths", default=None, help="Colon-separated literal paths.")
    parser.add_argument("--scope-instruction", default=None, help="Natural language scope.")
    parser.add_argument("--timeout", type=int, default=None, help="Timeout per agent call (seconds).")
    parser.add_argument("--refactoring-prompt", type=Path, default=None, help="Override default refactoring prompt.")
    parser.add_argument("--fix-prompt", type=Path, default=None, help="Override default fix prompt.")
    parser.add_argument("--show-agent-logs", action="store_true", help="Mirror agent output to terminal.")
    parser.add_argument("--show-command-logs", action="store_true", help="Mirror validation output to terminal.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root.",
    )
    parser.add_argument(
        "--use-branch",
        default=None,
        help=(
            "Branch to use for this run (checked out if it exists, "
            "created from main otherwise). Default: fresh timestamped branch."
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Continuous refactoring CLI for AI coding agents.",
    )
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser(
        "init",
        help="Register a project for continuous refactoring.",
    )
    init_parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Project path (default: current directory).",
    )
    init_parser.add_argument(
        "--live-migrations-dir",
        type=Path,
        default=None,
        help="Directory for live migration artifacts (repo-relative path).",
    )

    taste_parser = subparsers.add_parser(
        "taste",
        help="Manage refactoring taste files.",
    )
    taste_parser.add_argument(
        "--global",
        dest="global_",
        action="store_true",
        help="Use global taste file instead of project-level.",
    )
    taste_parser.add_argument(
        "--interview",
        action="store_true",
        help="Interview the user with an agent and write answers to the taste file.",
    )
    taste_parser.add_argument(
        "--with",
        dest="agent",
        choices=("codex", "claude"),
        default=None,
        help="Agent backend for --interview.",
    )
    taste_parser.add_argument(
        "--model",
        default=None,
        help="Model name for --interview.",
    )
    taste_parser.add_argument(
        "--effort",
        default=None,
        help="Effort level for --interview.",
    )
    taste_parser.add_argument(
        "--force",
        action="store_true",
        help="Allow overwriting a taste file with custom content (backup at .bak).",
    )

    run_once_parser = subparsers.add_parser(
        "run-once",
        help="Single refactoring attempt (one agent call, no fix retry).",
    )
    _add_common_args(run_once_parser)

    run_parser = subparsers.add_parser(
        "run",
        help="Continuous refactoring loop with fix-prompt retry.",
    )
    _add_common_args(run_parser)
    run_parser.add_argument(
        "--max-attempts",
        type=parse_max_attempts,
        default=None,
        help="Total attempts per target (1=no retry, 0=unlimited).",
    )
    run_parser.add_argument(
        "--max-refactors",
        type=int,
        default=None,
        help="Distinct targets to process.",
    )
    run_parser.add_argument(
        "--no-push",
        action="store_true",
        help="Skip push after successful commit.",
    )
    run_parser.add_argument(
        "--push-remote",
        default="origin",
        help="Git remote for pushing.",
    )
    run_parser.add_argument(
        "--commit-message-prefix",
        default="continuous refactor",
        help="Prefix for commit messages.",
    )
    run_parser.add_argument(
        "--max-consecutive-failures",
        type=int,
        default=3,
        help="Stop after N consecutive failures.",
    )

    return parser


def _validate_targeting(args: argparse.Namespace) -> None:
    has_targeting = args.targets or args.extensions or args.globs or args.paths
    if not has_targeting and not args.scope_instruction:
        print(
            "Error: --scope-instruction required when no "
            "--targets/--extensions/--globs/--paths",
            file=sys.stderr,
        )
        raise SystemExit(2)


def _handle_init(args: argparse.Namespace) -> None:
    from continuous_refactoring.config import (
        ensure_taste_file,
        register_project,
        set_live_migrations_dir,
    )

    path = (args.path or Path.cwd()).resolve()
    project = register_project(path)
    taste_path = project.project_dir / "taste.md"
    ensure_taste_file(taste_path)

    live_dir_arg: Path | None = getattr(args, "live_migrations_dir", None)
    if live_dir_arg is not None:
        resolved_live = (path / live_dir_arg).resolve()
        if not resolved_live.is_relative_to(path):
            print(
                f"Error: --live-migrations-dir must be inside the repo: {live_dir_arg}",
                file=sys.stderr,
            )
            raise SystemExit(2)
        relative = str(resolved_live.relative_to(path))
        resolved_live.mkdir(parents=True, exist_ok=True)
        set_live_migrations_dir(project.entry.uuid, relative)

    print(f"Project registered: {project.entry.uuid}")
    print(f"Data directory: {project.project_dir}")
    print(f"Taste file: {taste_path}")
    if live_dir_arg is not None:
        print(f"Live migrations dir: {resolved_live}")


def _resolve_taste_path(global_: bool) -> Path:
    from continuous_refactoring.config import (
        ContinuousRefactorError as ConfigError,
        global_dir,
        resolve_project,
    )

    if global_:
        path = global_dir() / "taste.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    try:
        project = resolve_project(Path.cwd().resolve())
    except ConfigError:
        print(
            "Error: project not initialized. Run 'continuous-refactoring init' first.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return project.project_dir / "taste.md"


def _handle_taste(args: argparse.Namespace) -> None:
    interview = getattr(args, "interview", False)
    agent_flags_set = any(
        getattr(args, name, None) is not None for name in ("agent", "model", "effort")
    )

    if not interview and agent_flags_set:
        print(
            "Error: --with/--model/--effort require --interview.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    if interview:
        missing = [
            flag
            for flag, value in (
                ("--with", getattr(args, "agent", None)),
                ("--model", getattr(args, "model", None)),
                ("--effort", getattr(args, "effort", None)),
            )
            if not value
        ]
        if missing:
            print(
                "Error: --interview requires " + ", ".join(missing) + ".",
                file=sys.stderr,
            )
            raise SystemExit(2)
        return _handle_taste_interview(args)

    from continuous_refactoring.config import ensure_taste_file

    path = _resolve_taste_path(args.global_)
    ensure_taste_file(path)
    print(str(path))


def _handle_taste_interview(args: argparse.Namespace) -> None:
    from continuous_refactoring.config import default_taste_text
    from continuous_refactoring.prompts import compose_interview_prompt

    path = _resolve_taste_path(args.global_)
    default_text = default_taste_text()
    existing: str | None = None
    file_exists = path.exists()
    if file_exists:
        current = path.read_text(encoding="utf-8")
        if current != default_text:
            if not args.force:
                print(
                    "Error: taste file already has custom content; "
                    "pass --force to overwrite (backup at taste.md.bak).",
                    file=sys.stderr,
                )
                raise SystemExit(1)
            backup = path.with_name(path.name + ".bak")
            backup.write_text(current, encoding="utf-8")
            existing = current

    path.parent.mkdir(parents=True, exist_ok=True)
    prompt = compose_interview_prompt(path, existing)
    repo_root = Path.cwd().resolve()
    returncode = run_agent_interactive(
        args.agent, args.model, args.effort, prompt, repo_root,
    )
    if returncode != 0:
        print(
            f"Error: interview agent exited with code {returncode}.",
            file=sys.stderr,
        )
        raise SystemExit(returncode)

    if not path.exists() or path.stat().st_size == 0:
        print(
            f"Error: interview agent did not write to {path}.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print(str(path))


def _handle_run_once(args: argparse.Namespace) -> None:
    _validate_targeting(args)
    try:
        raise SystemExit(run_once(args))
    except ContinuousRefactorError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error


def _handle_run(args: argparse.Namespace) -> None:
    _validate_targeting(args)
    if args.max_refactors is None and not args.targets:
        print(
            "Error: --max-refactors required when no --targets",
            file=sys.stderr,
        )
        raise SystemExit(2)
    try:
        raise SystemExit(run_loop(args))
    except ContinuousRefactorError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error


def cli_main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init":
        return _handle_init(args)
    if args.command == "taste":
        return _handle_taste(args)
    if args.command == "run-once":
        return _handle_run_once(args)
    if args.command == "run":
        return _handle_run(args)

    parser.print_help()
    raise SystemExit(1)
