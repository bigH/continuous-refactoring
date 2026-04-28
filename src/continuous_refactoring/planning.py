from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Literal

if TYPE_CHECKING:
    from continuous_refactoring.artifacts import RunArtifacts

from continuous_refactoring.agent import maybe_run_agent
from continuous_refactoring.artifacts import ContinuousRefactorError, iso_timestamp
from continuous_refactoring.effort import EffortBudget, require_effort_tier
from continuous_refactoring.migrations import (
    MigrationManifest,
    PhaseSpec,
    approaches_dir,
    intentional_skips_dir,
    migration_root,
    save_manifest,
)
from continuous_refactoring.prompts import PlanningStage, compose_planning_prompt

__all__ = ["PlanningOutcome", "run_planning"]

PlanningStatus = Literal["ready", "awaiting_human_review", "skipped"]

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


def _phase_precondition(content: str, phase_file: str) -> str:
    section = _phase_section_text(content, "Precondition")
    if section is not None:
        return section
    match = _PRECONDITION_LINE_RE.search(content)
    if match:
        return match.group(1).strip()
    return f"prerequisites in {phase_file} are met"


def _phase_required_effort(content: str, phase_file: str) -> str | None:
    raw = _phase_section_text(content, "Required Effort")
    if raw is None:
        match = _REQUIRED_EFFORT_LINE_RE.search(content)
        raw = match.group(1).strip() if match else None
    if raw is None:
        return None
    candidate = raw.strip().strip("`").split()[0].strip("`.,;:")
    return require_effort_tier(candidate, field=f"{phase_file} required_effort")


def _phase_effort_reason(content: str) -> str | None:
    section = _phase_section_text(content, "Effort Reason")
    if section is not None:
        return section
    match = _EFFORT_REASON_LINE_RE.search(content)
    if match:
        return match.group(1).strip()
    return None


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
        content = pf.read_text(encoding="utf-8")
        phases.append(
            PhaseSpec(
                name=name,
                file=pf.name,
                done=False,
                precondition=_phase_precondition(content, pf.name),
                required_effort=_phase_required_effort(content, pf.name),
                effort_reason=_phase_effort_reason(content),
            )
        )
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


def _build_context(target: str, mig_relative: Path, extra: str = "") -> str:
    parts = [f"Target: {target}", f"Migration directory: {mig_relative}"]
    if extra:
        parts.append(extra)
    return "\n\n".join(parts)


def _read_plan_text(plan_path: Path) -> str:
    return plan_path.read_text(encoding="utf-8") if plan_path.exists() else ""


def _join_nonempty(*parts: str) -> str:
    return "\n\n".join(part for part in parts if part)


def _read_approach_listing(live_dir: Path, migration_name: str) -> str:
    app_dir = approaches_dir(live_dir, migration_name)
    if not app_dir.exists():
        return ""
    return "\n\n".join(
        f"### {path.stem}\n{path.read_text(encoding='utf-8')}"
        for path in sorted(app_dir.glob("*.md"))
    )


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
# Main workflow
# ---------------------------------------------------------------------------


def run_planning(
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
) -> PlanningOutcome:
    mig_root = migration_root(live_dir, migration_name)
    mig_root.mkdir(parents=True, exist_ok=True)
    manifest_path = mig_root / "manifest.json"
    mig_relative = mig_root.relative_to(repo_root)

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

    agent_kw = dict(
        agent=agent,
        model=model,
        effort=effort,
        timeout=timeout,
        effort_metadata=effort_metadata,
        effort_budget=effort_budget,
    )
    plan_path = mig_root / "plan.md"
    state = _PlanningStageState(extra_context=extra_context)
    always_run_stages = (
        _PlanningStageSpec(
            prompt_stage="approaches",
            stage_label="approaches",
            build_context=lambda current: _build_context(
                target, mig_relative, current.extra_context
            ),
        ),
        _PlanningStageSpec(
            prompt_stage="pick-best",
            stage_label="pick-best",
            build_context=lambda current: _build_context(
                target,
                mig_relative,
                _join_nonempty(
                    current.extra_context,
                    f"Approaches:\n{current.approach_listing}",
                ),
            ),
        ),
        _PlanningStageSpec(
            prompt_stage="expand",
            stage_label="expand",
            build_context=lambda current: _build_context(
                target,
                mig_relative,
                _join_nonempty(
                    current.extra_context,
                    f"Chosen approach:\n{current.pick_stdout}",
                ),
            ),
            refresh_phase_listing=True,
        ),
        _PlanningStageSpec(
            prompt_stage="review",
            stage_label="review",
            build_context=lambda current: _build_context(
                target,
                mig_relative,
                _join_nonempty(current.extra_context, f"Plan:\n{_read_plan_text(plan_path)}"),
            ),
        ),
    )
    for spec in always_run_stages:
        manifest, _ = _run_pipeline_stage(
            spec,
            state,
            manifest,
            manifest_path,
            migration_name=migration_name,
            target=target,
            taste=taste,
            repo_root=repo_root,
            artifacts=artifacts,
            mig_root=mig_root,
            live_dir=live_dir,
            attempt=attempt,
            retry=retry,
            agent_kw=agent_kw,
        )
    review_stdout = state.review_stdout

    # Stage 5: revise + review again (only if first review had findings)
    if _review_has_findings(review_stdout):
        _run_stage(
            "expand", migration_name, target, taste,
            _build_context(
                target,
                mig_relative,
                _join_nonempty(
                    extra_context,
                    f"Review findings to address:\n{review_stdout}",
                ),
            ),
            repo_root,
            artifacts,
            attempt=attempt,
            retry=retry,
            stage_label="revise",
            **agent_kw,
        )
        manifest = _refresh_manifest(manifest, manifest_path, mig_root=mig_root)

        review_two_stdout = _run_stage(
            "review", migration_name, target, taste,
            _build_context(
                target,
                mig_relative,
                _join_nonempty(
                    extra_context,
                    f"Plan (revised):\n{_read_plan_text(plan_path)}",
                ),
            ),
            repo_root,
            artifacts,
            attempt=attempt,
            retry=retry,
            stage_label="review-2",
            **agent_kw,
        )
        _require_review_clear(review_two_stdout, "review-2")
        manifest = _refresh_manifest(manifest, manifest_path)

    # Stage 6: final-review
    final_stdout = _run_stage(
        "final-review", migration_name, target, taste,
        _build_context(
            target,
            mig_relative,
            _join_nonempty(extra_context, f"Plan:\n{_read_plan_text(plan_path)}"),
        ),
        repo_root, artifacts, attempt=attempt, retry=retry, **agent_kw,
    )

    try:
        decision, reason = _parse_final_decision(final_stdout)
    except ContinuousRefactorError as error:
        raise ContinuousRefactorError(
            f"planning.final-review failed: {error}"
        ) from error
    manifest = _refresh_manifest(manifest, manifest_path)

    if decision == "approve-auto":
        manifest = _refresh_manifest(manifest, manifest_path, status="ready")
        return PlanningOutcome(status="ready", reason=reason)

    if decision == "approve-needs-human":
        manifest = _refresh_manifest(
            manifest,
            manifest_path,
            status="ready",
            awaiting_human_review=True,
            human_review_reason=reason,
        )
        return PlanningOutcome(status="awaiting_human_review", reason=reason)

    # reject
    manifest = _refresh_manifest(manifest, manifest_path, status="skipped")
    _write_skip_file(live_dir, migration_name, target, reason)
    return PlanningOutcome(status="skipped", reason=reason)
