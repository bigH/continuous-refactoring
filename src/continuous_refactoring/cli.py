from __future__ import annotations

import argparse
import sys
from pathlib import Path

from continuous_refactoring.artifacts import ContinuousRefactorError


def parse_max_attempts(value: str) -> int:
    try:
        attempts = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    if attempts < 0:
        raise argparse.ArgumentTypeError("--max-attempts must be >= 0")
    return attempts


def _add_legacy_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--agent",
        choices=("codex", "claude"),
        required=True,
        help="Coding agent to run: codex or claude.",
    )
    parser.add_argument(
        "--model",
        required=True,
        help="Model name for the selected agent.",
    )
    parser.add_argument(
        "--effort",
        required=True,
        help="Effort level passed to the selected agent (e.g., xhigh/max).",
    )
    parser.add_argument(
        "--refactoring-prompt",
        required=True,
        type=Path,
        help="Prompt file used for the primary refactoring pass.",
    )
    parser.add_argument(
        "--fix-prompt",
        required=True,
        type=Path,
        help="Prompt file used after a failed test run before retrying.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root for all commands.",
    )
    parser.add_argument(
        "--validation-command",
        default="uv run pytest",
        help="Command used to run the full test suite.",
    )
    parser.add_argument(
        "--max-attempts",
        type=parse_max_attempts,
        default=None,
        help=(
            "Maximum attempt cycles before stopping. "
            "Omit or use 0 to run until interrupted."
        ),
    )
    parser.add_argument(
        "--commit-message-prefix",
        default="continuous refactor",
        help="Prefix for the commit message.",
    )
    parser.add_argument(
        "--push-remote",
        default="origin",
        help="Git remote for pushing.",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Run the loop and commit without pushing.",
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

    legacy_parser = subparsers.add_parser(
        "legacy-run",
        help="Run the legacy refactoring loop.",
    )
    _add_legacy_run_args(legacy_parser)

    return parser


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run iterative refactoring prompts with codex or claude.",
    )
    _add_legacy_run_args(parser)
    return parser.parse_args()


def _handle_init(args: argparse.Namespace) -> None:
    from continuous_refactoring.config import ensure_taste_file, register_project

    path = (args.path or Path.cwd()).resolve()
    project = register_project(path)
    taste_path = project.project_dir / "taste.md"
    ensure_taste_file(taste_path)
    print(f"Project registered: {project.entry.uuid}")
    print(f"Data directory: {project.project_dir}")
    print(f"Taste file: {taste_path}")


def _handle_taste(args: argparse.Namespace) -> None:
    from continuous_refactoring.config import (
        ContinuousRefactorError as ConfigError,
        ensure_taste_file,
        global_dir,
        resolve_project,
    )

    if args.global_:
        path = global_dir() / "taste.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        ensure_taste_file(path)
        print(str(path))
        return

    try:
        project = resolve_project(Path.cwd().resolve())
    except ConfigError:
        print(
            "Error: project not initialized. Run 'continuous-refactoring init' first.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    path = project.project_dir / "taste.md"
    ensure_taste_file(path)
    print(str(path))


def _handle_legacy_run(args: argparse.Namespace) -> None:
    from continuous_refactoring.loop import main

    try:
        raise SystemExit(main(args))
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
    if args.command == "legacy-run":
        return _handle_legacy_run(args)

    parser.print_help()
    raise SystemExit(1)
