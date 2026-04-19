from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

__all__ = [
    "build_parser",
    "cli_main",
    "parse_max_attempts",
    "parse_sleep_seconds",
]

from continuous_refactoring.agent import (
    run_agent_interactive,
    run_agent_interactive_until_settled,
)
from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.loop import (
    run_loop,
    run_migrations_focused_loop,
    run_once,
)

_TASTE_WARNING = "warning: taste out of date — run `continuous-refactoring taste --upgrade`"
_GLOBAL_TASTE_WARNING = (
    "warning: global taste is out of date — "
    "run 'continuous-refactoring taste --upgrade' to update."
)
_REVIEW_USAGE = "Usage: continuous-refactoring review {list,perform}"


def parse_max_attempts(value: str) -> int:
    try:
        attempts = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    if attempts < 0:
        raise argparse.ArgumentTypeError("--max-attempts must be >= 0")
    return attempts


def parse_sleep_seconds(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    if seconds < 0:
        raise argparse.ArgumentTypeError("--sleep must be >= 0")
    return seconds


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
    taste_mode = taste_parser.add_mutually_exclusive_group()
    taste_mode.add_argument(
        "--interview",
        action="store_true",
        help="Interview the user with an agent and write answers to the taste file.",
    )
    taste_mode.add_argument(
        "--upgrade",
        action="store_true",
        help="Upgrade taste to current version (interview about new dimensions only).",
    )
    taste_mode.add_argument(
        "--refine",
        action="store_true",
        help="Open an editing session to refine the taste file in place.",
    )
    taste_parser.add_argument(
        "--with",
        dest="agent",
        choices=("codex", "claude"),
        default=None,
        help="Agent backend for --interview, --upgrade, or --refine.",
    )
    taste_parser.add_argument(
        "--model",
        default=None,
        help="Model name for --interview, --upgrade, or --refine.",
    )
    taste_parser.add_argument(
        "--effort",
        default=None,
        help="Effort level for --interview, --upgrade, or --refine.",
    )
    taste_parser.add_argument(
        "--force",
        action="store_true",
        help="Allow --interview to overwrite a taste file with custom content (backup at .bak).",
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
        "--focus-on-live-migrations",
        action="store_true",
        help=(
            "Iterate only on live migrations until every one is done or blocked. "
            "Bypasses targeting and --max-refactors requirements."
        ),
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
    run_parser.add_argument(
        "--sleep",
        type=parse_sleep_seconds,
        default=0.0,
        help="Seconds to sleep between completed targets.",
    )

    subparsers.add_parser(
        "upgrade",
        help="Verify and upgrade global configuration.",
    )

    review_parser = subparsers.add_parser(
        "review",
        help="Review migrations awaiting human review.",
    )
    review_sub = review_parser.add_subparsers(dest="review_command")
    review_sub.add_parser("list", help="List migrations flagged for review.")
    perform_parser = review_sub.add_parser(
        "perform",
        help="Perform review on a flagged migration.",
    )
    perform_parser.add_argument("migration", help="Migration name to review.")
    perform_parser.add_argument(
        "--with", dest="agent", choices=("codex", "claude"), required=True,
        help="Agent backend.",
    )
    perform_parser.add_argument("--model", required=True, help="Model name.")
    perform_parser.add_argument("--effort", required=True, help="Effort level.")

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
    from continuous_refactoring.config import global_dir, resolve_project

    if global_:
        path = global_dir() / "taste.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    try:
        project = resolve_project(Path.cwd().resolve())
    except ContinuousRefactorError:
        print(
            "Error: project not initialized. Run 'continuous-refactoring init' first.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return project.project_dir / "taste.md"


def _taste_settle_path(path: Path) -> Path:
    return path.with_name(path.name + ".done")


def _active_taste_mode(args: argparse.Namespace) -> str | None:
    for mode in ("upgrade", "refine", "interview"):
        if getattr(args, mode, False):
            return mode
    return None


def _taste_agent_flags_set(args: argparse.Namespace) -> bool:
    return any(
        getattr(args, name, None) is not None for name in ("agent", "model", "effort")
    )


def _require_taste_action_flags(
    *,
    action: str,
    agent: str | None,
    model: str | None,
    effort: str | None,
) -> None:
    missing = [
        flag
        for flag, value in (
            ("--with", agent),
            ("--model", model),
            ("--effort", effort),
        )
        if not value
    ]
    if missing:
        print(
            f"Error: --{action} requires " + ", ".join(missing) + ".",
            file=sys.stderr,
        )
        raise SystemExit(2)


def _run_taste_agent(
    *,
    action: str,
    args: argparse.Namespace,
    prompt: str,
    path: Path,
) -> None:
    settle_path = _taste_settle_path(path)
    try:
        returncode = run_agent_interactive_until_settled(
            args.agent,
            args.model,
            args.effort,
            prompt,
            Path.cwd().resolve(),
            content_path=path,
            settle_path=settle_path,
        )
    except ContinuousRefactorError as error:
        print(f"Error: {action} agent did not settle: {error}.", file=sys.stderr)
        raise SystemExit(1) from error
    if returncode != 0:
        print(
            f"Error: {action} agent exited with code {returncode}.",
            file=sys.stderr,
        )
        raise SystemExit(returncode)

    if not path.exists() or path.stat().st_size == 0:
        print(
            f"Error: {action} agent did not write to {path}.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if settle_path.exists():
        settle_path.unlink()


def _handle_plain_taste(args: argparse.Namespace) -> None:
    from continuous_refactoring.config import ensure_taste_file

    path = _resolve_taste_path(args.global_)
    ensure_taste_file(path)
    print(str(path))


def _dispatch_taste_mode(mode: str, args: argparse.Namespace) -> None:
    if mode != "upgrade":
        _require_taste_action_flags(
            action=mode,
            agent=getattr(args, "agent", None),
            model=getattr(args, "model", None),
            effort=getattr(args, "effort", None),
        )
    _TASTE_MODE_HANDLERS[mode](args)


def _handle_taste(args: argparse.Namespace) -> None:
    mode = _active_taste_mode(args)

    if getattr(args, "force", False) and mode != "interview":
        print("Error: --force requires --interview.", file=sys.stderr)
        raise SystemExit(2)

    if mode is None:
        if _taste_agent_flags_set(args):
            print(
                "Error: --with/--model/--effort require --interview, --upgrade, or --refine.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        return _handle_plain_taste(args)

    return _dispatch_taste_mode(mode, args)


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
    prompt = compose_interview_prompt(path, _taste_settle_path(path), existing)
    _run_taste_agent(
        action="interview",
        args=args,
        prompt=prompt,
        path=path,
    )
    print(str(path))


def _handle_taste_refine(args: argparse.Namespace) -> None:
    from continuous_refactoring.config import default_taste_text
    from continuous_refactoring.prompts import compose_taste_refine_prompt

    path = _resolve_taste_path(args.global_)
    starting_taste = (
        path.read_text(encoding="utf-8") if path.exists() else default_taste_text()
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    prompt = compose_taste_refine_prompt(
        path,
        _taste_settle_path(path),
        starting_taste,
    )
    _run_taste_agent(
        action="refine",
        args=args,
        prompt=prompt,
        path=path,
    )
    print(str(path))


def _handle_taste_upgrade(args: argparse.Namespace) -> None:
    from continuous_refactoring.config import (
        TASTE_CURRENT_VERSION,
        parse_taste_version,
    )
    from continuous_refactoring.prompts import compose_taste_upgrade_prompt

    path = _resolve_taste_path(args.global_)

    existing: str | None = None
    stored_version: int | None = None
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        stored_version = parse_taste_version(existing)

    if stored_version == TASTE_CURRENT_VERSION:
        print("taste already current; use `taste --refine` to re-interview or refine it.")
        return

    _require_taste_action_flags(
        action="upgrade",
        agent=getattr(args, "agent", None),
        model=getattr(args, "model", None),
        effort=getattr(args, "effort", None),
    )

    prompt = compose_taste_upgrade_prompt(
        path,
        _taste_settle_path(path),
        existing,
        stored_version,
        TASTE_CURRENT_VERSION,
    )
    _run_taste_agent(
        action="upgrade",
        args=args,
        prompt=prompt,
        path=path,
    )
    print(str(path))


def _handle_upgrade(args: argparse.Namespace) -> None:
    from continuous_refactoring.config import (
        config_is_current,
        global_dir,
        load_manifest,
        save_manifest,
        taste_is_stale,
    )

    if not config_is_current():
        print(
            "Error: config version is absent or out of date.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    manifest = load_manifest()
    save_manifest(manifest)

    global_taste_path = global_dir() / "taste.md"
    if global_taste_path.exists():
        taste_text = global_taste_path.read_text(encoding="utf-8")
        if taste_is_stale(taste_text):
            print(_GLOBAL_TASTE_WARNING, file=sys.stderr)

def _resolve_review_context(*, error_code: int) -> Path:
    from continuous_refactoring.config import resolve_live_migrations_dir, resolve_project

    try:
        project = resolve_project(Path.cwd().resolve())
    except ContinuousRefactorError:
        print(
            "Error: project not initialized; no live-migrations-dir available.",
            file=sys.stderr,
        )
        raise SystemExit(error_code)

    live_dir = resolve_live_migrations_dir(project)
    if live_dir is None:
        print(
            "Error: no live-migrations-dir configured for this project.",
            file=sys.stderr,
        )
        raise SystemExit(error_code)

    return live_dir

def _handle_run_once(args: argparse.Namespace) -> None:
    _validate_targeting(args)
    _run_with_loop_errors(run_once, args)


def _handle_run(args: argparse.Namespace) -> None:
    if getattr(args, "focus_on_live_migrations", False):
        _run_with_loop_errors(run_migrations_focused_loop, args)
        return
    _validate_targeting(args)
    if args.max_refactors is None and not args.targets:
        print(
            "Error: --max-refactors required when no --targets",
            file=sys.stderr,
        )
        raise SystemExit(2)
    _run_with_loop_errors(run_loop, args)


def _handle_review_list() -> None:
    from continuous_refactoring.migrations import load_manifest as load_migration_manifest

    live_dir = _resolve_review_context(
        error_code=1,
    )

    if not live_dir.is_dir():
        return

    for child in sorted(live_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("__"):
            continue
        manifest_file = child / "manifest.json"
        if not manifest_file.exists():
            continue
        manifest = load_migration_manifest(manifest_file)
        if manifest.awaiting_human_review:
            reason = manifest.human_review_reason or "(no reason recorded)"
            print(
                f"{manifest.name}\t{manifest.status}\t"
                f"{manifest.current_phase}\t{manifest.last_touch}\t"
                f"{reason}"
            )


def _handle_review_perform(args: argparse.Namespace) -> None:
    from dataclasses import replace
    from continuous_refactoring.migrations import (
        load_manifest as load_migration_manifest,
        save_manifest as save_migration_manifest,
    )
    from continuous_refactoring.prompts import compose_review_perform_prompt

    live_dir = _resolve_review_context(
        error_code=2,
    )

    migration_name: str = args.migration
    migration_dir = live_dir / migration_name
    manifest_path = migration_dir / "manifest.json"
    if not manifest_path.exists():
        print(
            f"Error: migration '{migration_name}' does not exist.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    manifest = load_migration_manifest(manifest_path)
    if not manifest.awaiting_human_review:
        print(
            f"Error: migration '{migration_name}' is not flagged for review.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    plan_path = migration_dir / "plan.md"
    phase_file: str | None = None
    if 0 <= manifest.current_phase < len(manifest.phases):
        phase_file = manifest.phases[manifest.current_phase].file

    prompt = compose_review_perform_prompt(
        migration_name, manifest_path, plan_path, phase_file, manifest,
    )
    repo_root = Path.cwd().resolve()
    returncode = run_agent_interactive(
        args.agent, args.model, args.effort, prompt, repo_root,
    )
    if returncode != 0:
        print(
            f"Error: review agent exited with code {returncode}.",
            file=sys.stderr,
        )
        raise SystemExit(returncode)

    reloaded = load_migration_manifest(manifest_path)
    if reloaded.awaiting_human_review:
        print(
            f"Error: review of '{migration_name}' was not completed — "
            "awaiting_human_review is still set.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if reloaded.human_review_reason is not None:
        save_migration_manifest(
            replace(reloaded, human_review_reason=None), manifest_path,
        )


def _handle_review(args: argparse.Namespace) -> None:
    if args.review_command == "list":
        return _handle_review_list()
    if args.review_command == "perform":
        return _handle_review_perform(args)
    print(_REVIEW_USAGE, file=sys.stderr)
    raise SystemExit(2)


def _run_with_loop_errors(
    command: Callable[[argparse.Namespace], int],
    args: argparse.Namespace,
) -> None:
    try:
        raise SystemExit(command(args))
    except ContinuousRefactorError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error


def _maybe_warn_stale_taste() -> None:
    from continuous_refactoring.config import load_taste, resolve_project, taste_is_stale

    try:
        project = resolve_project(Path.cwd().resolve())
    except ContinuousRefactorError:
        project = None

    taste_text = load_taste(project)
    if taste_is_stale(taste_text):
        print(_TASTE_WARNING, file=sys.stderr)


def cli_main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is not None:
        _maybe_warn_stale_taste()

    handler = _COMMAND_HANDLERS.get(args.command) if args.command else None
    if handler is None:
        parser.print_help()
        raise SystemExit(1)

    return handler(args)


_COMMAND_HANDLERS: dict[str, Callable[[argparse.Namespace], None]] = {
    "init": lambda args: _handle_init(args),
    "taste": lambda args: _handle_taste(args),
    "upgrade": lambda args: _handle_upgrade(args),
    "review": lambda args: _handle_review(args),
    "run-once": lambda args: _handle_run_once(args),
    "run": lambda args: _handle_run(args),
}

_TASTE_MODE_HANDLERS: dict[str, Callable[[argparse.Namespace], None]] = {
    "interview": _handle_taste_interview,
    "refine": _handle_taste_refine,
    "upgrade": _handle_taste_upgrade,
}
