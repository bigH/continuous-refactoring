from __future__ import annotations

import argparse
import sys
from pathlib import Path

from continuous_refactoring.artifacts import ContinuousRefactorError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run iterative refactoring prompts with codex or claude.",
    )
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
    return parser.parse_args()


def parse_max_attempts(value: str) -> int:
    try:
        attempts = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    if attempts < 0:
        raise argparse.ArgumentTypeError("--max-attempts must be >= 0")
    return attempts


def cli_main() -> None:
    from continuous_refactoring.loop import main

    try:
        raise SystemExit(main())
    except ContinuousRefactorError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
