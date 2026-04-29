from __future__ import annotations

import argparse
import shutil
import sys
import uuid
from collections.abc import Callable
from importlib.metadata import version as metadata_version
from pathlib import Path

__all__ = [
    "build_parser",
    "cli_main",
    "parse_max_attempts",
    "parse_sleep_seconds",
]

from continuous_refactoring.agent import run_agent_interactive_until_settled
from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.effort import (
    DEFAULT_EFFORT,
    DEFAULT_MAX_ALLOWED_EFFORT,
    EFFORT_TIERS,
    parse_effort_arg,
    resolve_effort_budget,
)
from continuous_refactoring.loop import (
    run_loop,
    run_migrations_focused_loop,
    run_once,
)
from continuous_refactoring.review_cli import handle_review

_TASTE_WARNING = "warning: taste out of date — run `continuous-refactoring taste --upgrade`"
_GLOBAL_TASTE_WARNING = (
    "warning: global taste is out of date — "
    "run 'continuous-refactoring taste --upgrade' to update."
)


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
    parser.add_argument(
        "--default-effort",
        default=DEFAULT_EFFORT,
        type=parse_effort_arg,
        metavar="{" + ",".join(EFFORT_TIERS) + "}",
        help=f"Default effort level. Defaults to {DEFAULT_EFFORT}.",
    )
    parser.add_argument(
        "--max-allowed-effort",
        type=parse_effort_arg,
        default=DEFAULT_MAX_ALLOWED_EFFORT,
        metavar="{" + ",".join(EFFORT_TIERS) + "}",
        help=f"Highest effort this run may use. Defaults to {DEFAULT_MAX_ALLOWED_EFFORT}.",
    )
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


def _add_init_parser(subparsers: argparse._SubParsersAction) -> None:
    from continuous_refactoring.config import DEFAULT_REPO_TASTE_PATH

    init_parser = subparsers.add_parser(
        "init",
        help="Register a project for continuous refactoring.",
    )
    init_parser.set_defaults(handler=_handle_init)
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
    init_parser.add_argument(
        "--in-repo-taste",
        type=Path,
        nargs="?",
        const=Path(DEFAULT_REPO_TASTE_PATH),
        default=None,
        metavar="PATH",
        help=(
            "Store this project's taste file in the repo. "
            f"Defaults to {DEFAULT_REPO_TASTE_PATH}."
        ),
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Replace destination state when reconfiguring taste or live migrations.",
    )


def _add_taste_parser(subparsers: argparse._SubParsersAction) -> None:
    taste_parser = subparsers.add_parser(
        "taste",
        help="Manage refactoring taste files.",
    )
    taste_parser.set_defaults(handler=_handle_taste)
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


def _add_run_once_parser(subparsers: argparse._SubParsersAction) -> None:
    run_once_parser = subparsers.add_parser(
        "run-once",
        help="Single refactoring attempt (one agent call, no fix retry).",
    )
    run_once_parser.set_defaults(handler=_handle_run_once)
    _add_common_args(run_once_parser)


def _add_run_parser(subparsers: argparse._SubParsersAction) -> None:
    run_parser = subparsers.add_parser(
        "run",
        help="Continuous refactoring loop with fix-prompt retry.",
    )
    run_parser.set_defaults(handler=_handle_run)
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


def _add_review_parser(subparsers: argparse._SubParsersAction) -> None:
    review_parser = subparsers.add_parser(
        "review",
        help="Review migrations awaiting human review.",
    )
    review_parser.set_defaults(handler=handle_review)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Continuous refactoring CLI for AI coding agents.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"continuous-refactoring {metadata_version('continuous-refactoring')}",
    )
    subparsers = parser.add_subparsers(dest="command")

    _add_init_parser(subparsers)
    _add_taste_parser(subparsers)
    _add_run_once_parser(subparsers)
    _add_run_parser(subparsers)
    upgrade_parser = subparsers.add_parser(
        "upgrade",
        help="Verify and upgrade global configuration.",
    )
    upgrade_parser.set_defaults(handler=_handle_upgrade)
    _add_review_parser(subparsers)

    return parser


def _handle_init(args: argparse.Namespace) -> None:
    from continuous_refactoring.config import (
        ensure_taste_file,
        register_project,
        resolve_live_migrations_dir,
        resolve_project,
        resolve_project_taste_path,
        set_live_migrations_dir,
        set_repo_taste_path,
    )

    path = (args.path or Path.cwd()).resolve()
    in_repo_taste_arg: Path | None = getattr(args, "in_repo_taste", None)
    live_dir_arg: Path | None = getattr(args, "live_migrations_dir", None)
    force = bool(getattr(args, "force", False))
    repo_taste_relative: str | None = None
    repo_taste_resolved: Path | None = None
    resolved_live: Path | None = None
    live_dir_relative: str | None = None

    try:
        if in_repo_taste_arg is not None:
            repo_taste_resolved = (path / in_repo_taste_arg).resolve()
            if not repo_taste_resolved.is_relative_to(path):
                print(
                    f"Error: --in-repo-taste must be inside the repo: {in_repo_taste_arg}",
                    file=sys.stderr,
                )
                raise SystemExit(2)
            if repo_taste_resolved.exists() and not repo_taste_resolved.is_file():
                print(
                    f"Error: --in-repo-taste must point to a file: {in_repo_taste_arg}",
                    file=sys.stderr,
                )
                raise SystemExit(2)
            repo_taste_relative = str(repo_taste_resolved.relative_to(path))

        if live_dir_arg is not None:
            resolved_live = (path / live_dir_arg).resolve()
            if not resolved_live.is_relative_to(path):
                print(
                    f"Error: --live-migrations-dir must be inside the repo: {live_dir_arg}",
                    file=sys.stderr,
                )
                raise SystemExit(2)
            if resolved_live.exists() and not resolved_live.is_dir():
                print(
                    f"Error: --live-migrations-dir must point to a directory: {live_dir_arg}",
                    file=sys.stderr,
                )
                raise SystemExit(2)
            live_dir_relative = str(resolved_live.relative_to(path))

        project = register_project(path)
        if repo_taste_relative is not None:
            assert repo_taste_resolved is not None
            _configure_repo_taste(
                current=resolve_project_taste_path(project),
                destination=repo_taste_resolved,
                force=force,
                ensure_taste_file=ensure_taste_file,
            )
            set_repo_taste_path(project.entry.uuid, repo_taste_relative)
            project = resolve_project(path)

        taste_path = resolve_project_taste_path(project)
        ensure_taste_file(taste_path)

        if live_dir_arg is not None:
            assert resolved_live is not None
            assert live_dir_relative is not None
            _configure_live_migrations_dir(
                current=resolve_live_migrations_dir(project),
                destination=resolved_live,
                force=force,
            )
            set_live_migrations_dir(project.entry.uuid, live_dir_relative)
            project = resolve_project(path)
    except ContinuousRefactorError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error

    print(f"Project registered: {project.entry.uuid}")
    print(f"Data directory: {project.project_dir}")
    print(f"Taste file: {taste_path}")
    if live_dir_arg is not None:
        assert resolved_live is not None
        print(f"Live migrations dir: {resolved_live}")


def _configure_repo_taste(
    *,
    current: Path,
    destination: Path,
    force: bool,
    ensure_taste_file: Callable[[Path], Path],
) -> None:
    if not current.exists():
        ensure_taste_file(destination)
        return
    if current.resolve() == destination.resolve():
        return
    if not current.is_file():
        raise ContinuousRefactorError(
            f"Configured taste path is not a file: {current}"
        )
    if destination.exists() and not force:
        raise ContinuousRefactorError(
            "Taste destination already exists: "
            f"{destination}. Re-run init with --force to replace it."
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(current), str(destination))
    except OSError as exc:
        raise ContinuousRefactorError(
            f"Could not move taste file from {current} to {destination}."
        ) from exc


def _configure_live_migrations_dir(
    *,
    current: Path | None,
    destination: Path,
    force: bool,
) -> None:
    if current is None or not current.exists():
        destination.mkdir(parents=True, exist_ok=True)
        return
    if not current.is_dir():
        raise ContinuousRefactorError(
            f"Configured live migrations path is not a directory: {current}"
        )
    if current.resolve() == destination.resolve():
        return
    if (
        destination.resolve().is_relative_to(current.resolve())
        or current.resolve().is_relative_to(destination.resolve())
    ):
        raise ContinuousRefactorError(
            "Live migrations directory cannot be moved into itself or one of "
            f"its parents: {current} -> {destination}"
        )

    backup_destination: Path | None = None
    removed_empty_destination = False
    if destination.exists():
        if not destination.is_dir():
            raise ContinuousRefactorError(
                f"Live migrations destination is not a directory: {destination}"
            )
        if any(destination.iterdir()) and not force:
            raise ContinuousRefactorError(
                "Live migrations destination already exists and is not empty: "
                f"{destination}. Re-run init with --force to replace it."
            )
        if force:
            backup_name = (
                f".{destination.name}."
                f"continuous-refactoring-replaced-{uuid.uuid4().hex}"
            )
            backup_destination = destination.with_name(backup_name)
            destination.rename(backup_destination)
        else:
            destination.rmdir()
            removed_empty_destination = True

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(current), str(destination))
    except OSError as exc:
        if backup_destination is not None and not destination.exists():
            backup_destination.rename(destination)
        elif removed_empty_destination:
            destination.mkdir(parents=True, exist_ok=True)
        raise ContinuousRefactorError(
            "Could not move live migrations directory from "
            f"{current} to {destination}."
        ) from exc
    if backup_destination is not None:
        shutil.rmtree(backup_destination, ignore_errors=True)


def _resolve_taste_path(global_: bool) -> Path:
    from continuous_refactoring.config import (
        global_dir,
        resolve_project,
        resolve_project_taste_path,
    )

    if global_:
        path = global_dir() / "taste.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    try:
        project = resolve_project(Path.cwd().resolve())
    except ContinuousRefactorError as error:
        if not str(error).startswith("Project not registered:"):
            raise
        print(
            "Error: project not initialized. Run 'continuous-refactoring init' first.",
            file=sys.stderr,
        )
        raise SystemExit(1) from error
    return resolve_project_taste_path(project)


def _taste_settle_path(path: Path) -> Path:
    return path.with_name(path.name + ".done")


def _active_taste_mode(args: argparse.Namespace) -> str | None:
    for mode in _TASTE_MODE_HANDLERS:
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

    try:
        path = _resolve_taste_path(args.global_)
        ensure_taste_file(path)
    except ContinuousRefactorError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(str(path))


def _handle_current_taste_upgrade_if_noop(args: argparse.Namespace) -> bool:
    from continuous_refactoring.config import (
        TASTE_CURRENT_VERSION,
        parse_taste_version,
    )

    try:
        path = _resolve_taste_path(args.global_)
        stored_version = None
        if path.exists():
            stored_version = parse_taste_version(path.read_text(encoding="utf-8"))
    except (ContinuousRefactorError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    if stored_version != TASTE_CURRENT_VERSION:
        return False
    print("taste already current; use `taste --refine` to re-interview or refine it.")
    return True


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

    if mode == "upgrade" and _handle_current_taste_upgrade_if_noop(args):
        return
    _require_taste_action_flags(
        action=mode,
        agent=getattr(args, "agent", None),
        model=getattr(args, "model", None),
        effort=getattr(args, "effort", None),
    )
    return _TASTE_MODE_HANDLERS[mode](args)


def _handle_taste_interview(args: argparse.Namespace) -> None:
    from continuous_refactoring.config import default_taste_text
    from continuous_refactoring.prompts import compose_interview_prompt

    try:
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
    except ContinuousRefactorError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(str(path))


def _handle_taste_refine(args: argparse.Namespace) -> None:
    from continuous_refactoring.config import default_taste_text
    from continuous_refactoring.prompts import compose_taste_refine_prompt

    try:
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
    except ContinuousRefactorError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(str(path))


def _handle_taste_upgrade(args: argparse.Namespace) -> None:
    from continuous_refactoring.config import (
        TASTE_CURRENT_VERSION,
        parse_taste_version,
    )
    from continuous_refactoring.prompts import compose_taste_upgrade_prompt

    try:
        path = _resolve_taste_path(args.global_)

        existing: str | None = None
        stored_version: int | None = None
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            stored_version = parse_taste_version(existing)

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
    except ContinuousRefactorError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(str(path))


def _handle_upgrade(args: argparse.Namespace) -> None:
    from continuous_refactoring.config import (
        config_is_current,
        global_dir,
        load_manifest,
        save_manifest,
        taste_is_stale,
    )

    try:
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
    except (ContinuousRefactorError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


def _require_targeting_or_scope(args: argparse.Namespace) -> None:
    has_targeting = args.targets or args.extensions or args.globs or args.paths
    if not has_targeting and not args.scope_instruction:
        print(
            "Error: --scope-instruction required when no "
            "--targets/--extensions/--globs/--paths",
            file=sys.stderr,
        )
        raise SystemExit(2)


def _exit_with_loop_result(
    command: Callable[[argparse.Namespace], int],
    args: argparse.Namespace,
) -> None:
    try:
        raise SystemExit(command(args))
    except ContinuousRefactorError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error


def _normalize_run_effort_args(args: argparse.Namespace) -> None:
    default_effort = getattr(args, "default_effort", getattr(args, "effort", None))
    max_allowed_effort = getattr(args, "max_allowed_effort", None)
    try:
        budget = resolve_effort_budget(default_effort, max_allowed_effort)
    except ContinuousRefactorError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
    args.default_effort = budget.default_effort
    args.effort = budget.default_effort
    args.max_allowed_effort = budget.max_allowed_effort


def _handle_run_once(args: argparse.Namespace) -> None:
    _normalize_run_effort_args(args)
    _require_targeting_or_scope(args)
    _exit_with_loop_result(run_once, args)


def _handle_run(args: argparse.Namespace) -> None:
    _normalize_run_effort_args(args)
    if getattr(args, "focus_on_live_migrations", False):
        _exit_with_loop_result(run_migrations_focused_loop, args)
        return
    _require_targeting_or_scope(args)
    if args.max_refactors is None and not args.targets:
        print(
            "Error: --max-refactors required when no --targets",
            file=sys.stderr,
        )
        raise SystemExit(2)
    _exit_with_loop_result(run_loop, args)


def _maybe_warn_stale_taste() -> None:
    from continuous_refactoring.config import load_taste, resolve_project, taste_is_stale

    try:
        project = resolve_project(Path.cwd().resolve())
    except ContinuousRefactorError:
        project = None

    try:
        taste_text = load_taste(project)
    except ContinuousRefactorError:
        return
    if taste_is_stale(taste_text):
        print(_TASTE_WARNING, file=sys.stderr)


def cli_main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is not None:
        _maybe_warn_stale_taste()

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        raise SystemExit(1)

    return handler(args)

_TASTE_MODE_HANDLERS: dict[str, Callable[[argparse.Namespace], None]] = {
    "interview": _handle_taste_interview,
    "refine": _handle_taste_refine,
    "upgrade": _handle_taste_upgrade,
}
