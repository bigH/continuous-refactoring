from __future__ import annotations

import argparse
import sys
from pathlib import Path

__all__ = [
    "build_parser",
    "cli_main",
    "parse_args",
    "parse_max_attempts",
]

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
        help="Retry attempts per target (0=unlimited).",
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run iterative refactoring prompts with codex or claude.",
    )
    _add_legacy_run_args(parser)
    return parser.parse_args()


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


def _handle_run_once(args: argparse.Namespace) -> None:
    _validate_targeting(args)
    from continuous_refactoring.loop import run_once

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
    if args.max_refactors is not None and args.max_refactors > 10 and not args.targets:
        args.max_refactors = 10
    from continuous_refactoring.loop import run_loop

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
