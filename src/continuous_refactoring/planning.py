from __future__ import annotations

import re
import shutil
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Literal

if TYPE_CHECKING:
    from continuous_refactoring.artifacts import RunArtifacts

from continuous_refactoring.agent import maybe_run_agent
from continuous_refactoring.artifacts import ContinuousRefactorError, iso_timestamp
from continuous_refactoring.config import resolve_project
from continuous_refactoring.effort import EffortBudget, require_effort_tier
from continuous_refactoring.migrations import (
    MigrationManifest,
    PhaseSpec,
    approaches_dir,
    intentional_skips_dir,
    load_manifest,
    migration_root,
    save_manifest,
)
from continuous_refactoring.planning_publish import (
    PlanningPublishError,
    PlanningPublishRequest,
    PlanningPublishResult,
    capture_live_snapshot,
    prepare_planning_workspace,
    publish_planning_workspace,
)
from continuous_refactoring.planning_state import (
    FeedbackSource,
    PlanningCursor,
    PlanningState,
    PlanningStep,
    append_planning_feedback,
    complete_planning_step,
    load_planning_state,
    new_planning_state,
    planning_state_path,
    planning_step_stdout,
    reopen_planning_for_revise,
    save_planning_state,
    write_planning_stage_stdout,
)
from continuous_refactoring.prompts import PlanningStage, compose_planning_prompt

__all__ = [
    "PlanningOutcome",
    "PlanningRefineRequest",
    "PlanningStepResult",
    "run_next_planning_step",
    "run_refine_planning_step",
]

PlanningStatus = Literal["ready", "awaiting_human_review", "skipped"]
PlanningStepStatus = Literal["published", "blocked", "failed"]

_FINAL_DECISION_RE = re.compile(
    r"^final-decision:\s*(approve-auto|approve-needs-human|reject)(?:\s*[—-]\s*(.+))?$",
    re.IGNORECASE,
)

_PRECONDITION_LINE_RE = re.compile(
    r"^precondition:\s*(.+)$", re.IGNORECASE | re.MULTILINE,
)
_REQUIRED_EFFORT_LINE_RE = re.compile(
    r"^required_effort:\s*(.+)$", re.IGNORECASE | re.MULTILINE,
)
_EFFORT_REASON_LINE_RE = re.compile(
    r"^effort_reason:\s*(.+)$", re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class PlanningOutcome:
    status: PlanningStatus
    reason: str


@dataclass(frozen=True)
class PlanningStepResult:
    status: PlanningStepStatus
    migration_name: str
    step: PlanningStep
    next_step: PlanningCursor
    reason: str
    terminal_outcome: PlanningOutcome | None = None
    publish_result: PlanningPublishResult | None = None


@dataclass(frozen=True)
class PlanningRefineRequest:
    migration_name: str
    feedback_text: str
    feedback_source: FeedbackSource
    taste: str
    repo_root: Path
    live_dir: Path
    artifacts: RunArtifacts
    agent: str
    model: str
    effort: str
    timeout: int | None = None
    attempt: int = 1
    retry: int = 1
    effort_budget: EffortBudget | None = None
    effort_metadata: dict[str, object] | None = None


@dataclass(frozen=True)
class _PhaseMetadata:
    precondition: str
    required_effort: str | None
    effort_reason: str | None


@dataclass(frozen=True)
class _PlanningStageSpec:
    prompt_stage: PlanningStage
    stage_label: str
    build_context: Callable[["_PlanningStageState"], str]
    refresh_phase_listing: bool = False


@dataclass
class _PlanningStageState:
    extra_context: str
    approach_listing: str = ""
    pick_stdout: str = ""
    review_stdout: str = ""


# ---------------------------------------------------------------------------
# Output parsers
# ---------------------------------------------------------------------------


def _parse_final_decision(stdout: str) -> tuple[str, str]:
    for line in reversed(stdout.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        match = _FINAL_DECISION_RE.match(stripped)
        if not match:
            continue
        decision = match.group(1).lower()
        reason = match.group(2).strip() if match.group(2) else decision
        return decision, reason
    raise ContinuousRefactorError("Final review produced no output")


def _review_has_findings(stdout: str) -> bool:
    has_non_empty = False
    for line in stdout.splitlines():
        stripped = line.strip().lower()
        if not stripped:
            continue
        has_non_empty = True
        if "no findings" in stripped:
            return False
    return has_non_empty


def _require_review_clear(stdout: str, stage_label: str) -> None:
    if _review_has_findings(stdout):
        raise ContinuousRefactorError(
            f"planning.{stage_label} failed: revised plan still has findings"
        )


# ---------------------------------------------------------------------------
# Phase discovery
# ---------------------------------------------------------------------------


def _phase_section_text(content: str, heading: str) -> str | None:
    match = re.search(
        rf"^##\s+{re.escape(heading)}\s*$\n(?P<body>.*?)(?=^##\s+|\Z)",
        content,
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    if not match:
        return None
    body = match.group("body")
    normalized = " ".join(line.strip() for line in body.splitlines() if line.strip())
    return normalized or None


def _phase_field(
    content: str,
    *,
    heading: str,
    line_re: re.Pattern[str],
) -> str | None:
    section = _phase_section_text(content, heading)
    if section is not None:
        return section
    match = line_re.search(content)
    if match:
        return match.group(1).strip()
    return None


def _parse_phase_metadata(content: str, phase_file: str) -> _PhaseMetadata:
    precondition = _phase_field(
        content,
        heading="Precondition",
        line_re=_PRECONDITION_LINE_RE,
    )
    raw_required_effort = _phase_field(
        content,
        heading="Required Effort",
        line_re=_REQUIRED_EFFORT_LINE_RE,
    )
    effort_reason = _phase_field(
        content,
        heading="Effort Reason",
        line_re=_EFFORT_REASON_LINE_RE,
    )
    required_effort = None
    if raw_required_effort is not None:
        candidate = raw_required_effort.strip().strip("`").split()[0].strip("`.,;:")
        required_effort = require_effort_tier(
            candidate,
            field=f"{phase_file} required_effort",
        )
    return _PhaseMetadata(
        precondition=precondition or f"prerequisites in {phase_file} are met",
        required_effort=required_effort,
        effort_reason=effort_reason,
    )


def _phase_precondition(content: str, phase_file: str) -> str:
    return _parse_phase_metadata(content, phase_file).precondition


def _phase_required_effort(content: str, phase_file: str) -> str | None:
    return _parse_phase_metadata(content, phase_file).required_effort


def _phase_effort_reason(content: str) -> str | None:
    return _parse_phase_metadata(content, "<phase>").effort_reason


def _phase_spec_from_file(phase_file: Path) -> PhaseSpec:
    content = phase_file.read_text(encoding="utf-8")
    metadata = _parse_phase_metadata(content, phase_file.name)
    name = phase_file.stem.split("-", 2)[2]
    return PhaseSpec(
        name=name,
        file=phase_file.name,
        done=False,
        precondition=metadata.precondition,
        required_effort=metadata.required_effort,
        effort_reason=metadata.effort_reason,
    )

def _discover_phase_files(mig_root: Path) -> tuple[PhaseSpec, ...]:
    phase_files: list[tuple[int, Path]] = []
    for pf in mig_root.glob("phase-*-*.md"):
        parts = pf.stem.split("-", 2)
        if len(parts) < 3 or not parts[1].isdigit():
            continue
        phase_files.append((int(parts[1]), pf))

    phase_files.sort(key=lambda item: item[0])
    phases: list[PhaseSpec] = []
    seen_names: set[str] = set()
    for _, pf in phase_files:
        parts = pf.stem.split("-", 2)
        name = parts[2]
        if name in seen_names:
            raise ContinuousRefactorError(
                f"Duplicate phase names are not allowed in {mig_root.name}: {name}"
            )
        seen_names.add(name)
        phases.append(_phase_spec_from_file(pf))
    return tuple(phases)


# ---------------------------------------------------------------------------
# Skip file
# ---------------------------------------------------------------------------


def _write_skip_file(
    live_dir: Path,
    migration_name: str,
    target: str,
    reason: str,
) -> None:
    skips_dir = intentional_skips_dir(live_dir)
    skips_dir.mkdir(parents=True, exist_ok=True)
    (skips_dir / f"{migration_name}.md").write_text(
        f"# Intentional Skip: {migration_name}\n\n"
        f"## Target\n{target}\n\n"
        f"## Blocker Reason\n{reason}\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Stage runner
# ---------------------------------------------------------------------------


def _run_stage(
    stage: PlanningStage,
    migration_name: str,
    target: str,
    taste: str,
    context: str,
    repo_root: Path,
    artifacts: RunArtifacts,
    *,
    attempt: int,
    retry: int,
    agent: str,
    model: str,
    effort: str,
    timeout: int | None,
    effort_metadata: dict[str, object] | None = None,
    effort_budget: EffortBudget | None = None,
    stage_label: str | None = None,
) -> str:
    prompt = compose_planning_prompt(
        stage,
        migration_name,
        taste,
        context,
        effort_budget=effort_budget,
    )
    label = stage_label or stage
    call_role = f"planning.{label}"
    stage_dir = artifacts.root / "planning" / label
    stage_dir.mkdir(parents=True, exist_ok=True)

    artifacts.log_call_started(
        attempt=attempt,
        retry=retry,
        target=target,
        call_role=call_role,
        effort=effort_metadata,
    )

    try:
        result = maybe_run_agent(
            agent=agent,
            model=model,
            effort=effort,
            prompt=prompt,
            repo_root=repo_root,
            stdout_path=stage_dir / "agent.stdout.log",
            stderr_path=stage_dir / "agent.stderr.log",
            last_message_path=(
                stage_dir / "agent-last-message.md" if agent == "codex" else None
            ),
            mirror_to_terminal=False,
            timeout=timeout,
        )
    except ContinuousRefactorError as error:
        artifacts.log_call_finished(
            attempt=attempt,
            retry=retry,
            target=target,
            call_role=call_role,
            status="failed",
            level="WARN",
            summary=str(error),
            effort=effort_metadata,
        )
        raise ContinuousRefactorError(f"{call_role} failed: {error}") from error

    if result.returncode != 0:
        artifacts.log_call_finished(
            attempt=attempt,
            retry=retry,
            target=target,
            call_role=call_role,
            status="failed",
            level="WARN",
            returncode=result.returncode,
            summary=f"{agent} exited with code {result.returncode}",
            effort=effort_metadata,
        )
        raise ContinuousRefactorError(
            f"{call_role} failed: {agent} exited with code {result.returncode}"
        )

    artifacts.log_call_finished(
        attempt=attempt,
        retry=retry,
        target=target,
        call_role=call_role,
        status="finished",
        returncode=result.returncode,
        effort=effort_metadata,
    )
    return result.stdout


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


def _build_context(
    target: str,
    mig_relative: Path,
    extra: str = "",
    *,
    work_dir: Path | None = None,
    live_mig_root: Path | None = None,
) -> str:
    parts = [
        f"Target: {target}",
        f"Migration directory: {mig_relative}",
        "Read and write all migration planning artifacts inside that directory.",
    ]
    if work_dir is not None:
        live_dir = live_mig_root or work_dir
        parts.extend(
            [
                f"Staged work dir: {work_dir}",
                f"Work dir: {work_dir}",
                f"Live migration dir: {live_dir}",
                "The staged work dir is the planning workspace; successful "
                "steps are atomically published by the harness.",
                "Writable target: staged work dir only.",
                "Writable target: work dir only.",
                "The live migration directory is read-only reference material.",
                "Do not mutate the live migration directory.",
                "Resume input is the last published .planning/state.json plus "
                "accepted stdout under .planning/stages/.",
                "failed current-step output, stdout/stderr, and partial work "
                "are run artifacts only; they are not resume input.",
            ]
        )
    if extra:
        parts.append(extra)
    return "\n\n".join(parts)


def _read_plan_text(plan_path: Path) -> str:
    return plan_path.read_text(encoding="utf-8") if plan_path.exists() else ""


def _join_nonempty(*parts: str) -> str:
    return "\n\n".join(part for part in parts if part)


def _display_migration_path(repo_root: Path, mig_root: Path) -> Path:
    try:
        return mig_root.relative_to(repo_root)
    except ValueError:
        return mig_root


def _read_approach_listing(live_dir: Path, migration_name: str) -> str:
    app_dir = approaches_dir(live_dir, migration_name)
    if not app_dir.exists():
        return ""
    return "\n\n".join(
        f"### {path.stem}\n{path.read_text(encoding='utf-8')}"
        for path in sorted(app_dir.glob("*.md"))
    )


def _durable_stdout_context(
    title: str,
    state: PlanningState,
    repo_root: Path,
    mig_root: Path,
    step: str,
    *,
    published_migration_root: Path | None = None,
) -> str:
    stdout_ref, stdout = planning_step_stdout(
        state,
        repo_root,
        step,
        state_path=planning_state_path(mig_root),
        published_migration_root=published_migration_root,
    )
    return f"{title} (from {stdout_ref}):\n{stdout}"


def _build_durable_planning_context(
    *,
    repo_root: Path,
    live_dir: Path,
    migration_name: str,
    state: PlanningState,
    extra_context: str = "",
    published_migration_root: Path | None = None,
) -> str:
    mig_root = migration_root(live_dir, migration_name)
    mig_relative = _display_migration_path(repo_root, mig_root)
    plan_path = mig_root / "plan.md"

    if state.next_step == "approaches":
        step_context = ""
    elif state.next_step == "pick-best":
        step_context = f"Approaches:\n{_read_approach_listing(live_dir, migration_name)}"
    elif state.next_step == "expand":
        step_context = _durable_stdout_context(
            "Chosen approach",
            state,
            repo_root,
            mig_root,
            "pick-best",
            published_migration_root=published_migration_root,
        )
    elif state.next_step == "review":
        step_context = f"Plan:\n{_read_plan_text(plan_path)}"
    elif state.next_step == "revise":
        if not state.revision_base_step_counts:
            step_context = _durable_stdout_context(
                "Review findings to address",
                state,
                repo_root,
                mig_root,
                "review",
                published_migration_root=published_migration_root,
            )
        else:
            step_context = _latest_feedback_context(state)
    elif state.next_step == "review-2":
        step_context = f"Plan (revised):\n{_read_plan_text(plan_path)}"
    elif state.next_step == "final-review":
        step_context = f"Plan:\n{_read_plan_text(plan_path)}"
    else:
        raise ContinuousRefactorError(
            f"Planning state is terminal; no prompt context for {state.next_step!r}"
        )

    return _build_context(
        state.target,
        mig_relative,
        _join_nonempty(extra_context, step_context),
        work_dir=mig_root,
        live_mig_root=published_migration_root,
    )


def _latest_feedback_context(state: PlanningState) -> str:
    if not state.feedback:
        raise ContinuousRefactorError("Planning refinement requires user feedback")
    return f"User refinement feedback to address:\n{state.feedback[-1].text}"


def _record_completed_planning_step(
    state: PlanningState,
    *,
    repo_root: Path,
    mig_root: Path,
    published_migration_root: Path | None = None,
    stage_label: str,
    outcome: str,
    stdout: str,
    agent: str,
    model: str,
    effort: str,
    final_reason: str | None = None,
) -> PlanningState:
    outputs = write_planning_stage_stdout(
        repo_root,
        mig_root,
        stage_label,
        stdout,
        published_migration_root=published_migration_root,
    )
    updated = complete_planning_step(
        state,
        stage_label,
        outcome,
        outputs,
        completed_at=iso_timestamp(),
        agent=agent,
        model=model,
        effort=effort,
        final_reason=final_reason,
    )
    save_planning_state(
        updated,
        planning_state_path(mig_root),
        repo_root=repo_root,
        published_migration_root=published_migration_root,
    )
    return updated


def _run_pipeline_stage(
    spec: _PlanningStageSpec,
    state: _PlanningStageState,
    manifest: MigrationManifest,
    manifest_path: Path,
    *,
    migration_name: str,
    target: str,
    taste: str,
    repo_root: Path,
    artifacts: RunArtifacts,
    mig_root: Path,
    live_dir: Path,
    attempt: int,
    retry: int,
    agent_kw: dict[str, object],
) -> tuple[MigrationManifest, str]:
    stdout = _run_stage(
        spec.prompt_stage,
        migration_name,
        target,
        taste,
        spec.build_context(state),
        repo_root,
        artifacts,
        attempt=attempt,
        retry=retry,
        **agent_kw,
    )
    if spec.stage_label == "approaches":
        state.approach_listing = _read_approach_listing(live_dir, migration_name)
    elif spec.stage_label == "pick-best":
        state.pick_stdout = stdout
    elif spec.stage_label == "review":
        state.review_stdout = stdout
    refresh_kw = {"mig_root": mig_root} if spec.refresh_phase_listing else {}
    return _refresh_manifest(manifest, manifest_path, **refresh_kw), stdout


def _refresh_manifest(
    manifest: MigrationManifest,
    manifest_path: Path,
    *,
    mig_root: Path | None = None,
    **changes: object,
) -> MigrationManifest:
    if mig_root is not None:
        phases = _discover_phase_files(mig_root)
        changes["phases"] = phases
        current_phase = changes.get("current_phase", manifest.current_phase)
        if isinstance(current_phase, str):
            phase_names = {phase.name for phase in phases}
            if not current_phase and phases:
                changes["current_phase"] = phases[0].name
            elif current_phase and current_phase not in phase_names:
                changes["current_phase"] = phases[0].name if phases else ""
    updated = replace(manifest, last_touch=iso_timestamp(), **changes)
    save_manifest(updated, manifest_path)
    return updated


# ---------------------------------------------------------------------------
# One-step workflow
# ---------------------------------------------------------------------------


def run_next_planning_step(
    migration_name: str,
    target: str,
    taste: str,
    repo_root: Path,
    live_dir: Path,
    artifacts: RunArtifacts,
    *,
    attempt: int = 1,
    retry: int = 1,
    agent: str,
    model: str,
    effort: str,
    timeout: int | None,
    effort_budget: EffortBudget | None = None,
    effort_metadata: dict[str, object] | None = None,
    extra_context: str = "",
) -> PlanningStepResult:
    live_mig_root = migration_root(live_dir, migration_name)
    base_snapshot_id = capture_live_snapshot(repo_root, live_dir, migration_name)
    workspace_root = _prepare_step_workspace(
        repo_root,
        artifacts,
        migration_name,
        live_mig_root,
    )
    manifest, state = _load_or_seed_step_snapshot(
        workspace_root,
        live_mig_root,
        migration_name=migration_name,
        target=target,
        repo_root=repo_root,
    )
    if state.next_step not in _STEP_PROMPT_STAGES:
        raise ContinuousRefactorError(
            f"Planning state is terminal; no next step for {state.next_step!r}"
        )

    step = state.next_step
    manifest, state, terminal_outcome = _execute_step_in_workspace(
        manifest,
        state,
        migration_name=migration_name,
        taste=taste,
        repo_root=repo_root,
        workspace_root=workspace_root,
        live_mig_root=live_mig_root,
        artifacts=artifacts,
        attempt=attempt,
        retry=retry,
        agent=agent,
        model=model,
        effort=effort,
        timeout=timeout,
        effort_budget=effort_budget,
        effort_metadata=effort_metadata,
        extra_context=extra_context,
    )

    validation_mode = "ready-publish" if manifest.status == "ready" else "planning-snapshot"
    try:
        publish_result = publish_planning_workspace(
            PlanningPublishRequest(
                repo_root=repo_root,
                live_migrations_dir=live_dir,
                slug=migration_name,
                workspace_dir=workspace_root,
                base_snapshot_id=base_snapshot_id,
                validation_mode=validation_mode,
                operation=f"planning.{step}",
            )
        )
    except PlanningPublishError as error:
        return PlanningStepResult(
            status=error.result.status,
            migration_name=migration_name,
            step=step,
            next_step=state.next_step,
            reason=error.result.reason,
            terminal_outcome=None,
            publish_result=error.result,
        )

    return PlanningStepResult(
        status="published",
        migration_name=migration_name,
        step=step,
        next_step=state.next_step,
        reason=_planning_step_reason(step, state, terminal_outcome),
        terminal_outcome=terminal_outcome,
        publish_result=publish_result,
    )


def run_refine_planning_step(request: PlanningRefineRequest) -> PlanningStepResult:
    live_mig_root = migration_root(request.live_dir, request.migration_name)
    base_snapshot_id = capture_live_snapshot(
        request.repo_root,
        request.live_dir,
        request.migration_name,
    )
    workspace_root = _prepare_step_workspace(
        request.repo_root,
        request.artifacts,
        request.migration_name,
        live_mig_root,
    )
    manifest, state = _load_refine_snapshot(
        workspace_root,
        live_mig_root,
        repo_root=request.repo_root,
        migration_name=request.migration_name,
    )
    manifest, state = _prepare_refine_state(
        manifest,
        state,
        workspace_root=workspace_root,
        live_mig_root=live_mig_root,
        repo_root=request.repo_root,
        feedback_text=request.feedback_text,
        feedback_source=request.feedback_source,
    )
    if state.next_step not in _STEP_PROMPT_STAGES:
        raise ContinuousRefactorError(
            f"Planning state is terminal; no next step for {state.next_step!r}"
        )

    step = state.next_step
    manifest, state, terminal_outcome = _execute_step_in_workspace(
        manifest,
        state,
        migration_name=request.migration_name,
        taste=request.taste,
        repo_root=request.repo_root,
        workspace_root=workspace_root,
        live_mig_root=live_mig_root,
        artifacts=request.artifacts,
        attempt=request.attempt,
        retry=request.retry,
        agent=request.agent,
        model=request.model,
        effort=request.effort,
        timeout=request.timeout,
        effort_budget=request.effort_budget,
        effort_metadata=request.effort_metadata,
        extra_context=_user_feedback_context(request.feedback_text),
    )

    validation_mode = "ready-publish" if manifest.status == "ready" else "planning-snapshot"
    try:
        publish_result = publish_planning_workspace(
            PlanningPublishRequest(
                repo_root=request.repo_root,
                live_migrations_dir=request.live_dir,
                slug=request.migration_name,
                workspace_dir=workspace_root,
                base_snapshot_id=base_snapshot_id,
                validation_mode=validation_mode,
                operation=f"migration.refine.{step}",
            )
        )
    except PlanningPublishError as error:
        return PlanningStepResult(
            status=error.result.status,
            migration_name=request.migration_name,
            step=step,
            next_step=state.next_step,
            reason=error.result.reason,
            terminal_outcome=None,
            publish_result=error.result,
        )

    return PlanningStepResult(
        status="published",
        migration_name=request.migration_name,
        step=step,
        next_step=state.next_step,
        reason=_planning_step_reason(step, state, terminal_outcome),
        terminal_outcome=terminal_outcome,
        publish_result=publish_result,
    )


_STEP_PROMPT_STAGES: dict[str, PlanningStage] = {
    "approaches": "approaches",
    "pick-best": "pick-best",
    "expand": "expand",
    "review": "review",
    "revise": "expand",
    "review-2": "review",
    "final-review": "final-review",
}


def _prepare_step_workspace(
    repo_root: Path,
    artifacts: RunArtifacts,
    migration_name: str,
    live_mig_root: Path,
) -> Path:
    project_state_dir = _planning_project_state_dir(repo_root, artifacts)
    workspace = prepare_planning_workspace(
        project_state_dir,
        migration_name,
        f"{artifacts.run_id}-{uuid.uuid4().hex}",
    )
    if live_mig_root.exists():
        shutil.copytree(live_mig_root, workspace.root, dirs_exist_ok=True)
    return workspace.root


def _planning_project_state_dir(repo_root: Path, artifacts: RunArtifacts) -> Path:
    try:
        return resolve_project(repo_root).project_dir
    except ContinuousRefactorError:
        return artifacts.root / "project-state"


def _load_or_seed_step_snapshot(
    workspace_root: Path,
    live_mig_root: Path,
    *,
    migration_name: str,
    target: str,
    repo_root: Path,
) -> tuple[MigrationManifest, PlanningState]:
    manifest_path = workspace_root / "manifest.json"
    state_path = planning_state_path(workspace_root)
    if manifest_path.exists():
        manifest = load_manifest(manifest_path)
        if manifest.status != "planning":
            raise ContinuousRefactorError(
                f"Planning snapshot {migration_name!r} is not in planning status"
            )
        if not state_path.exists():
            raise ContinuousRefactorError(
                f"Planning snapshot {migration_name!r} is missing .planning/state.json"
            )
        state = load_planning_state(
            repo_root,
            state_path,
            published_migration_root=live_mig_root,
        )
        return manifest, state

    now = iso_timestamp()
    manifest = MigrationManifest(
        name=migration_name,
        created_at=now,
        last_touch=now,
        wake_up_on=None,
        awaiting_human_review=False,
        status="planning",
        current_phase="",
        phases=(),
    )
    save_manifest(manifest, manifest_path)
    state = new_planning_state(target, now=now)
    save_planning_state(
        state,
        state_path,
        repo_root=repo_root,
        published_migration_root=live_mig_root,
    )
    return manifest, state


def _load_refine_snapshot(
    workspace_root: Path,
    live_mig_root: Path,
    *,
    repo_root: Path,
    migration_name: str,
) -> tuple[MigrationManifest, PlanningState]:
    manifest_path = workspace_root / "manifest.json"
    state_path = planning_state_path(workspace_root)
    if not manifest_path.exists():
        raise ContinuousRefactorError(f"Migration {migration_name!r} has no manifest")
    if not state_path.exists():
        raise ContinuousRefactorError(
            f"Migration {migration_name!r} is missing .planning/state.json"
        )
    manifest = load_manifest(manifest_path)
    state = load_planning_state(
        repo_root,
        state_path,
        published_migration_root=live_mig_root,
    )
    return manifest, state


def _prepare_refine_state(
    manifest: MigrationManifest,
    state: PlanningState,
    *,
    workspace_root: Path,
    live_mig_root: Path,
    repo_root: Path,
    feedback_text: str,
    feedback_source: FeedbackSource,
) -> tuple[MigrationManifest, PlanningState]:
    _require_refine_eligible(manifest)
    state = append_planning_feedback(state, feedback_text, feedback_source)
    if manifest.status == "ready":
        state = reopen_planning_for_revise(state)
        manifest = _refresh_manifest(
            manifest,
            workspace_root / "manifest.json",
            status="planning",
            awaiting_human_review=False,
            human_review_reason=None,
            cooldown_until=None,
            current_phase=manifest.phases[0].name,
        )
    elif state.next_step not in _STEP_PROMPT_STAGES:
        raise ContinuousRefactorError(
            f"Planning state is terminal; no next step for {state.next_step!r}"
        )
    save_planning_state(
        state,
        planning_state_path(workspace_root),
        repo_root=repo_root,
        published_migration_root=live_mig_root,
    )
    return manifest, state


def _require_refine_eligible(manifest: MigrationManifest) -> None:
    if any(phase.done for phase in manifest.phases):
        raise ContinuousRefactorError(
            f"Migration {manifest.name!r} has completed phase work and cannot be refined"
        )
    if manifest.status == "planning":
        return
    if manifest.status != "ready":
        raise ContinuousRefactorError(
            f"Migration {manifest.name!r} has status {manifest.status!r}; "
            "only planning or unexecuted ready migrations can be refined"
        )
    if not manifest.phases:
        raise ContinuousRefactorError(
            f"Migration {manifest.name!r} has no phases and cannot be refined"
        )
    first_phase = manifest.phases[0]
    if manifest.current_phase != first_phase.name:
        raise ContinuousRefactorError(
            f"Migration {manifest.name!r} has already advanced past its first phase"
        )


def _user_feedback_context(text: str) -> str:
    return f"User refinement feedback:\n{text}"


def _execute_step_in_workspace(
    manifest: MigrationManifest,
    state: PlanningState,
    *,
    migration_name: str,
    taste: str,
    repo_root: Path,
    workspace_root: Path,
    live_mig_root: Path,
    artifacts: RunArtifacts,
    attempt: int,
    retry: int,
    agent: str,
    model: str,
    effort: str,
    timeout: int | None,
    effort_budget: EffortBudget | None,
    effort_metadata: dict[str, object] | None,
    extra_context: str,
) -> tuple[MigrationManifest, PlanningState, PlanningOutcome | None]:
    step = state.next_step
    if step not in _STEP_PROMPT_STAGES:
        raise ContinuousRefactorError(f"Planning step {step!r} cannot be executed")
    prompt_stage = _STEP_PROMPT_STAGES[step]
    context = _build_durable_planning_context(
        repo_root=repo_root,
        live_dir=workspace_root.parent,
        migration_name=migration_name,
        state=state,
        extra_context=extra_context,
        published_migration_root=live_mig_root,
    )
    stdout = _run_stage(
        prompt_stage,
        migration_name,
        state.target,
        taste,
        context,
        repo_root,
        artifacts,
        attempt=attempt,
        retry=retry,
        agent=agent,
        model=model,
        effort=effort,
        timeout=timeout,
        effort_metadata=effort_metadata,
        effort_budget=effort_budget,
        stage_label=step,
    )

    outcome, final_reason = _step_outcome(step, stdout)
    manifest = _refresh_manifest(
        manifest,
        workspace_root / "manifest.json",
        mig_root=workspace_root if step in ("expand", "revise") else None,
    )
    state = _record_completed_planning_step(
        state,
        repo_root=repo_root,
        mig_root=workspace_root,
        published_migration_root=live_mig_root,
        stage_label=step,
        outcome=outcome,
        stdout=stdout,
        agent=agent,
        model=model,
        effort=effort,
        final_reason=final_reason,
    )
    terminal_outcome = _terminal_outcome(state)
    if terminal_outcome is None:
        return manifest, state, None
    manifest = _apply_terminal_manifest_state(
        manifest,
        workspace_root / "manifest.json",
        workspace_root=workspace_root,
        live_dir=workspace_root.parent,
        migration_name=migration_name,
        target=state.target,
        outcome=terminal_outcome,
    )
    return manifest, state, terminal_outcome


def _step_outcome(step: PlanningStep, stdout: str) -> tuple[str, str | None]:
    if step == "review":
        return ("findings" if _review_has_findings(stdout) else "clear"), None
    if step == "review-2":
        _require_review_clear(stdout, "review-2")
        return "clear", None
    if step == "final-review":
        try:
            return _parse_final_decision(stdout)
        except ContinuousRefactorError as error:
            raise ContinuousRefactorError(
                f"planning.final-review failed: {error}"
            ) from error
    return "completed", None


def _terminal_outcome(state: PlanningState) -> PlanningOutcome | None:
    if state.next_step == "terminal-ready":
        return PlanningOutcome(status="ready", reason=state.final_reason or "ready")
    if state.next_step == "terminal-ready-awaiting-human":
        return PlanningOutcome(
            status="awaiting_human_review",
            reason=state.final_reason or "awaiting human review",
        )
    if state.next_step == "terminal-skipped":
        return PlanningOutcome(status="skipped", reason=state.final_reason or "skipped")
    return None


def _apply_terminal_manifest_state(
    manifest: MigrationManifest,
    manifest_path: Path,
    *,
    workspace_root: Path,
    live_dir: Path,
    migration_name: str,
    target: str,
    outcome: PlanningOutcome,
) -> MigrationManifest:
    if outcome.status == "ready":
        return _refresh_manifest(
            manifest,
            manifest_path,
            status="ready",
            awaiting_human_review=False,
            human_review_reason=None,
        )
    if outcome.status == "awaiting_human_review":
        return _refresh_manifest(
            manifest,
            manifest_path,
            status="ready",
            awaiting_human_review=True,
            human_review_reason=outcome.reason,
        )

    (workspace_root / "intentional-skip.md").write_text(
        f"# Intentional Skip: {migration_name}\n\n"
        f"## Target\n{target}\n\n"
        f"## Blocker Reason\n{outcome.reason}\n",
        encoding="utf-8",
    )
    return _refresh_manifest(manifest, manifest_path, status="skipped")


def _planning_step_reason(
    step: PlanningStep,
    state: PlanningState,
    terminal_outcome: PlanningOutcome | None,
) -> str:
    if terminal_outcome is not None:
        return terminal_outcome.reason
    return f"planning.{step} accepted; next step: {state.next_step}"
