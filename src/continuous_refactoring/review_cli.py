from __future__ import annotations

import argparse
import shutil
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from continuous_refactoring.agent import run_agent_interactive
from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.config import (
    load_taste,
    resolve_live_migrations_dir,
    resolve_project,
)
from continuous_refactoring.migration_cli import MigrationTarget, resolve_migration_target
from continuous_refactoring.migration_consistency import (
    check_migration_consistency,
    has_blocking_consistency_findings,
    iter_visible_migration_dirs,
)
from continuous_refactoring.migrations import (
    load_manifest as load_migration_manifest,
    phase_file_reference,
    resolve_current_phase,
)
from continuous_refactoring.planning_publish import (
    PlanningPublishError,
    PlanningPublishRequest,
    PlanningPublishResult,
    capture_live_snapshot,
    prepare_planning_workspace,
    publish_planning_workspace,
)
from continuous_refactoring.prompts import compose_review_perform_prompt

__all__ = [
    "StagedReviewRequest",
    "handle_review",
    "handle_review_list",
    "handle_review_perform",
    "handle_staged_migration_review",
    "perform_staged_migration_review",
]

_REVIEW_USAGE = "Usage: continuous-refactoring review {list,perform}"


@dataclass(frozen=True)
class _ReviewCliContext:
    repo_root: Path
    live_dir: Path
    project_state_dir: Path


@dataclass(frozen=True)
class StagedReviewRequest:
    repo_root: Path
    live_dir: Path
    target: MigrationTarget
    project_state_dir: Path
    agent: str
    model: str
    effort: str
    taste: str


class _ReviewCliError(ContinuousRefactorError):
    def __init__(self, message: str, exit_code: int) -> None:
        self.exit_code = exit_code
        super().__init__(message)


def _resolve_review_context(*, error_code: int) -> _ReviewCliContext:
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

    return _ReviewCliContext(
        repo_root=Path(project.entry.path).resolve(),
        live_dir=live_dir,
        project_state_dir=project.project_dir,
    )


def handle_review_list() -> None:
    context = _resolve_review_context(error_code=1)
    live_dir = context.live_dir

    if not live_dir.is_dir():
        return

    for child in iter_visible_migration_dirs(live_dir):
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
    context = _resolve_review_context(error_code=2)
    try:
        target = resolve_migration_target(
            live_dir=context.live_dir,
            repo_root=context.repo_root,
            value=args.migration,
        )
    except ContinuousRefactorError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(2) from error

    try:
        taste = load_taste(resolve_project(context.repo_root))
    except ContinuousRefactorError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error

    handle_staged_migration_review(
        StagedReviewRequest(
            repo_root=context.repo_root,
            live_dir=context.live_dir,
            target=target,
            project_state_dir=context.project_state_dir,
            agent=args.agent,
            model=args.model,
            effort=args.effort,
            taste=taste,
        )
    )


def handle_staged_migration_review(
    request: StagedReviewRequest,
) -> PlanningPublishResult:
    try:
        return perform_staged_migration_review(request)
    except _ReviewCliError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(error.exit_code) from error
    except PlanningPublishError as error:
        print(
            f"Error: {_review_publish_error_message(error, request.target.slug)}",
            file=sys.stderr,
        )
        raise SystemExit(1) from error
    except ContinuousRefactorError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


def perform_staged_migration_review(
    request: StagedReviewRequest,
) -> PlanningPublishResult:
    manifest_path = request.target.path / "manifest.json"
    if not manifest_path.exists():
        raise _ReviewCliError(
            f"migration '{request.target.slug}' does not exist.",
            2,
        )

    manifest = load_migration_manifest(manifest_path)
    if not manifest.awaiting_human_review:
        raise _ReviewCliError(
            f"migration '{request.target.slug}' is not flagged for review.",
            2,
        )

    base_snapshot_id = capture_live_snapshot(
        request.repo_root,
        request.live_dir,
        request.target.slug,
    )
    workspace = prepare_planning_workspace(
        request.project_state_dir,
        request.target.slug,
        f"review-{uuid.uuid4().hex}",
    )
    try:
        shutil.copytree(request.target.path, workspace.root, dirs_exist_ok=True)
    except (OSError, shutil.Error) as error:
        raise ContinuousRefactorError(
            f"Could not copy migration to review workspace {workspace.root}: {error}"
        ) from error

    phase = resolve_current_phase(manifest) if manifest.current_phase else None
    prompt = compose_review_perform_prompt(
        request.target.slug,
        request.repo_root,
        workspace.root,
        request.target.path,
        phase,
        manifest,
        request.taste,
    )
    returncode = run_agent_interactive(
        request.agent,
        request.model,
        request.effort,
        prompt,
        workspace.root,
    )
    if returncode != 0:
        raise _ReviewCliError(
            f"review agent exited with code {returncode}.",
            returncode,
        )

    _require_consistent_review_workspace(workspace.root)
    reloaded = load_migration_manifest(workspace.root / "manifest.json")
    if reloaded.awaiting_human_review:
        raise _ReviewCliError(
            f"review of '{request.target.slug}' was not completed; "
            "awaiting_human_review is still set.",
            1,
        )
    if reloaded.human_review_reason is not None:
        raise _ReviewCliError(
            f"review of '{request.target.slug}' was not completed; "
            "human_review_reason is still set.",
            1,
        )

    return publish_planning_workspace(
        PlanningPublishRequest(
            repo_root=request.repo_root,
            live_migrations_dir=request.live_dir,
            slug=request.target.slug,
            workspace_dir=workspace.root,
            base_snapshot_id=base_snapshot_id,
            validation_mode="ready-publish",
            operation="migration.review",
        )
    )


def _require_consistent_review_workspace(workspace_root: Path) -> None:
    findings = check_migration_consistency(workspace_root, mode="ready-publish")
    if not has_blocking_consistency_findings(findings):
        return
    details = "; ".join(
        f"{finding.code}: {finding.path}: {finding.message}"
        for finding in findings
        if finding.severity == "error"
    )
    raise _ReviewCliError(
        f"review workspace validation failed: {details}",
        1,
    )


def _review_publish_error_message(error: PlanningPublishError, slug: str) -> str:
    message = str(error)
    if "stale base snapshot" not in error.result.reason:
        return message
    return (
        f"{message}\n"
        "Live migration changed while review was running. "
        f"Run `continuous-refactoring migration doctor {slug}` if unsure, then "
        f"rerun `continuous-refactoring migration review {slug} ...`."
    )


def handle_review(args: argparse.Namespace) -> None:
    if args.review_command == "list":
        return handle_review_list()
    if args.review_command == "perform":
        return handle_review_perform(args)
    print(_REVIEW_USAGE, file=sys.stderr)
    raise SystemExit(2)
