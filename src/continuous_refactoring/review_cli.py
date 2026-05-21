from __future__ import annotations

import shutil
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from continuous_refactoring.agent import run_agent_interactive
from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.migration_cli import MigrationTarget
from continuous_refactoring.migration_consistency import (
    check_migration_consistency,
    has_blocking_consistency_findings,
)
from continuous_refactoring.migrations import (
    MigrationManifest,
    load_manifest as load_migration_manifest,
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
from continuous_refactoring.prompts import compose_migration_review_prompt

__all__ = [
    "StagedReviewRequest",
    "handle_staged_migration_review",
]


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


def handle_staged_migration_review(
    request: StagedReviewRequest,
) -> PlanningPublishResult:
    try:
        return _run_staged_migration_review(request)
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


def _run_staged_migration_review(
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
            _not_awaiting_review_message(request.target.slug, manifest),
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
    prompt = compose_migration_review_prompt(
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


def _not_awaiting_review_message(slug: str, manifest: MigrationManifest) -> str:
    message = (
        f"migration '{slug}' is not awaiting human review. "
        "Reviewable migrations are listed by "
        "`continuous-refactoring migration list --awaiting-review`."
    )
    if _is_refine_eligible(manifest):
        return (
            f"{message} To revise this migration instead, run "
            f"`continuous-refactoring migration refine {slug} ...`."
        )
    return (
        f"{message} `continuous-refactoring migration refine {slug} ...` "
        "is only available for planning or unexecuted ready migrations."
    )


def _is_refine_eligible(manifest: MigrationManifest) -> bool:
    if any(phase.done for phase in manifest.phases):
        return False
    if manifest.status == "planning":
        return True
    if manifest.status != "ready":
        return False
    if not manifest.phases:
        return False
    return manifest.current_phase == manifest.phases[0].name


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
