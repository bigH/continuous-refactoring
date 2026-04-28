from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from continuous_refactoring.agent import run_agent_interactive
from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.config import resolve_live_migrations_dir, resolve_project
from continuous_refactoring.migrations import (
    load_manifest as load_migration_manifest,
    phase_file_reference,
    resolve_current_phase,
    save_manifest as save_migration_manifest,
)
from continuous_refactoring.prompts import compose_review_perform_prompt

__all__ = [
    "handle_review",
    "handle_review_list",
    "handle_review_perform",
]

_REVIEW_USAGE = "Usage: continuous-refactoring review {list,perform}"


def _resolve_review_context(*, error_code: int) -> Path:
    try:
        project = resolve_project(Path.cwd().resolve())
    except ContinuousRefactorError:
        print(
            "Error: project not initialized; no live-migrations-dir available.",
            file=sys.stderr,
        )
        raise SystemExit(error_code)
    try:
        live_dir = resolve_live_migrations_dir(project)
    except ContinuousRefactorError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(error_code)
    if live_dir is None:
        print(
            "Error: no live-migrations-dir configured for this project.",
            file=sys.stderr,
        )
        raise SystemExit(error_code)

    return live_dir


def handle_review_list() -> None:
    live_dir = _resolve_review_context(error_code=1)

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
            phase = resolve_current_phase(manifest) if manifest.current_phase else None
            phase_file = phase_file_reference(phase) if phase is not None else "(none)"
            phase_name = phase.name if phase is not None else "(none)"
            print(
                f"{manifest.name}\t{manifest.status}\t"
                f"{phase_file}\t{phase_name}\t{manifest.last_touch}\t"
                f"{reason}"
            )


def handle_review_perform(args: argparse.Namespace) -> None:
    live_dir = _resolve_review_context(error_code=2)

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
    phase = resolve_current_phase(manifest) if manifest.current_phase else None

    prompt = compose_review_perform_prompt(
        migration_name, manifest_path, plan_path, phase, manifest,
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


def handle_review(args: argparse.Namespace) -> None:
    if args.review_command == "list":
        return handle_review_list()
    if args.review_command == "perform":
        return handle_review_perform(args)
    print(_REVIEW_USAGE, file=sys.stderr)
    raise SystemExit(2)
