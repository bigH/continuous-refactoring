from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from continuous_refactoring.artifacts import RunArtifacts

from continuous_refactoring.agent import maybe_run_agent
from continuous_refactoring.artifacts import ContinuousRefactorError, iso_timestamp
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

_READY_WHEN_RE = re.compile(
    r"^(?:ready[_ ]?when):\s*(.+)$", re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class PlanningOutcome:
    status: PlanningStatus
    reason: str


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


# ---------------------------------------------------------------------------
# Phase discovery
# ---------------------------------------------------------------------------


def _discover_phase_files(mig_root: Path) -> tuple[PhaseSpec, ...]:
    phase_files: list[tuple[int, Path]] = []
    for pf in mig_root.glob("phase-*-*.md"):
        parts = pf.stem.split("-", 2)
        if len(parts) < 3 or not parts[1].isdigit():
            continue
        phase_files.append((int(parts[1]), pf))

    phase_files.sort(key=lambda item: item[0])
    phases: list[PhaseSpec] = []
    for _, pf in phase_files:
        parts = pf.stem.split("-", 2)
        name = parts[2]
        content = pf.read_text(encoding="utf-8")
        ready_match = _READY_WHEN_RE.search(content)
        ready_when = (
            ready_match.group(1).strip()
            if ready_match
            else f"phase {parts[1]} prerequisites met"
        )
        phases.append(PhaseSpec(
            name=name,
            file=pf.name,
            done=False,
            ready_when=ready_when,
        ))
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
    taste: str,
    context: str,
    repo_root: Path,
    artifacts: RunArtifacts,
    *,
    agent: str,
    model: str,
    effort: str,
    timeout: int | None,
    stage_label: str | None = None,
) -> str:
    prompt = compose_planning_prompt(stage, migration_name, taste, context)
    label = stage_label or stage
    stage_dir = artifacts.root / "planning" / label
    stage_dir.mkdir(parents=True, exist_ok=True)

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

    if result.returncode != 0:
        raise ContinuousRefactorError(
            f"Planning stage '{label}' failed with exit code {result.returncode}"
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


def _bump_manifest(manifest: MigrationManifest, manifest_path: Path) -> MigrationManifest:
    manifest = replace(manifest, last_touch=iso_timestamp())
    save_manifest(manifest, manifest_path)
    return manifest


def _plan_text(plan_path: Path) -> str:
    return plan_path.read_text(encoding="utf-8") if plan_path.exists() else ""


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
    agent: str,
    model: str,
    effort: str,
    timeout: int | None,
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
        current_phase=0,
        phases=(),
    )
    save_manifest(manifest, manifest_path)

    agent_kw = dict(agent=agent, model=model, effort=effort, timeout=timeout)

    # Stage 1: approaches
    _run_stage(
        "approaches", migration_name, taste,
        _build_context(target, mig_relative, extra_context),
        repo_root, artifacts, **agent_kw,
    )
    manifest = _bump_manifest(manifest, manifest_path)

    # Stage 2: pick-best
    app_dir = approaches_dir(live_dir, migration_name)
    approach_listing = ""
    if app_dir.exists():
        approach_listing = "\n\n".join(
            f"### {f.stem}\n{f.read_text(encoding='utf-8')}"
            for f in sorted(app_dir.glob("*.md"))
        )
    pick_stdout = _run_stage(
        "pick-best", migration_name, taste,
        _build_context(
            target,
            mig_relative,
            "\n\n".join(
                part for part in (extra_context, f"Approaches:\n{approach_listing}") if part
            ),
        ),
        repo_root, artifacts, **agent_kw,
    )
    manifest = _bump_manifest(manifest, manifest_path)

    # Stage 3: expand
    _run_stage(
        "expand", migration_name, taste,
        _build_context(
            target,
            mig_relative,
            "\n\n".join(
                part for part in (extra_context, f"Chosen approach:\n{pick_stdout}") if part
            ),
        ),
        repo_root, artifacts, **agent_kw,
    )
    phases = _discover_phase_files(mig_root)
    manifest = _bump_manifest(replace(manifest, phases=phases), manifest_path)

    # Stage 4: review
    plan_path = mig_root / "plan.md"
    plan_text = _plan_text(plan_path)
    review_stdout = _run_stage(
        "review", migration_name, taste,
        _build_context(
            target,
            mig_relative,
            "\n\n".join(
                part for part in (extra_context, f"Plan:\n{plan_text}") if part
            ),
        ),
        repo_root, artifacts, **agent_kw,
    )
    manifest = _bump_manifest(manifest, manifest_path)

    # Stage 5: revise + review again (only if first review had findings)
    if _review_has_findings(review_stdout):
        _run_stage(
            "expand", migration_name, taste,
            _build_context(
                target,
                mig_relative,
                "\n\n".join(
                    part
                    for part in (
                        extra_context,
                        f"Review findings to address:\n{review_stdout}",
                    )
                    if part
                ),
            ),
            repo_root, artifacts, stage_label="revise", **agent_kw,
        )
        phases = _discover_phase_files(mig_root)
        manifest = _bump_manifest(replace(manifest, phases=phases), manifest_path)

        plan_text = _plan_text(plan_path)
        _run_stage(
            "review", migration_name, taste,
            _build_context(
                target,
                mig_relative,
                "\n\n".join(
                    part
                    for part in (extra_context, f"Plan (revised):\n{plan_text}")
                    if part
                ),
            ),
            repo_root, artifacts, stage_label="review-2", **agent_kw,
        )
        manifest = _bump_manifest(manifest, manifest_path)

    # Stage 6: final-review
    plan_text = _plan_text(plan_path)
    final_stdout = _run_stage(
        "final-review", migration_name, taste,
        _build_context(
            target,
            mig_relative,
            "\n\n".join(
                part for part in (extra_context, f"Plan:\n{plan_text}") if part
            ),
        ),
        repo_root, artifacts, **agent_kw,
    )

    decision, reason = _parse_final_decision(final_stdout)
    manifest = _bump_manifest(manifest, manifest_path)

    if decision == "approve-auto":
        manifest = replace(manifest, status="ready")
        save_manifest(manifest, manifest_path)
        return PlanningOutcome(status="ready", reason=reason)

    if decision == "approve-needs-human":
        manifest = replace(manifest, status="ready", awaiting_human_review=True)
        save_manifest(manifest, manifest_path)
        return PlanningOutcome(status="awaiting_human_review", reason=reason)

    # reject
    manifest = replace(manifest, status="skipped")
    save_manifest(manifest, manifest_path)
    _write_skip_file(live_dir, migration_name, target, reason)
    return PlanningOutcome(status="skipped", reason=reason)
