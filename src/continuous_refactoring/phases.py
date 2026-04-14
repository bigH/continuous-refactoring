from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from continuous_refactoring.artifacts import RunArtifacts
    from continuous_refactoring.migrations import MigrationManifest, PhaseSpec

__all__ = [
    "ExecutePhaseOutcome",
    "ReadyVerdict",
    "check_phase_ready",
    "execute_phase",
    "generate_phase_branch_name",
]

from continuous_refactoring.agent import maybe_run_agent, run_tests, summarize_output
from continuous_refactoring.artifacts import ContinuousRefactorError, iso_timestamp
from continuous_refactoring.git import get_head_sha, revert_to
from continuous_refactoring.migrations import migration_root, save_manifest
from continuous_refactoring.prompts import (
    compose_phase_execution_prompt,
    compose_phase_ready_prompt,
)

ReadyVerdict = Literal["yes", "no", "unverifiable"]

_READY_RE = re.compile(r"^ready:\s*(yes|no|unverifiable)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ExecutePhaseOutcome:
    status: Literal["done", "awaiting_human_review", "failed"]
    reason: str


def _parse_ready_verdict(stdout: str) -> tuple[ReadyVerdict, str]:
    for line in reversed(stdout.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        match = _READY_RE.match(stripped)
        if match:
            verdict: ReadyVerdict = match.group(1).lower()  # type: ignore[assignment]
            reason = stripped[match.end():].lstrip(" \u2014-").strip() or verdict
            return verdict, reason
        raise ContinuousRefactorError(
            f"Phase ready-check produced unrecognised output: {stripped!r}"
        )
    raise ContinuousRefactorError("Phase ready-check produced no output")


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def generate_phase_branch_name(
    migration_name: str, phase_index: int, phase_name: str,
) -> str:
    return (
        f"migration/{_slugify(migration_name)}"
        f"/phase-{phase_index}-{_slugify(phase_name)}"
    )


def check_phase_ready(
    phase: PhaseSpec,
    manifest: MigrationManifest,
    taste: str,
    repo_root: Path,
    artifacts: RunArtifacts,
    *,
    agent: str,
    model: str,
    effort: str,
    timeout: int | None,
) -> tuple[ReadyVerdict, str]:
    prompt = compose_phase_ready_prompt(phase, manifest)
    check_dir = artifacts.root / "phase-ready-check"
    check_dir.mkdir(parents=True, exist_ok=True)

    result = maybe_run_agent(
        agent=agent,
        model=model,
        effort=effort,
        prompt=prompt,
        repo_root=repo_root,
        stdout_path=check_dir / "agent.stdout.log",
        stderr_path=check_dir / "agent.stderr.log",
        last_message_path=(
            check_dir / "agent-last-message.md" if agent == "codex" else None
        ),
        mirror_to_terminal=False,
        timeout=timeout,
    )

    if result.returncode != 0:
        raise ContinuousRefactorError(
            f"Phase ready-check agent failed with exit code {result.returncode}"
        )

    return _parse_ready_verdict(result.stdout)


def _find_phase_index(manifest: MigrationManifest, phase: PhaseSpec) -> int:
    for i, p in enumerate(manifest.phases):
        if p.name == phase.name and p.file == phase.file:
            return i
    raise ContinuousRefactorError(f"Phase {phase.name!r} not found in manifest")


def execute_phase(
    phase: PhaseSpec,
    manifest: MigrationManifest,
    target_or_none: str | None,
    taste: str,
    repo_root: Path,
    live_dir: Path,
    artifacts: RunArtifacts,
    *,
    agent: str,
    model: str,
    effort: str,
    timeout: int | None,
) -> ExecutePhaseOutcome:
    prompt = compose_phase_execution_prompt(phase, manifest, taste)
    phase_dir = artifacts.root / "phase-execute"
    phase_dir.mkdir(parents=True, exist_ok=True)

    head_before = get_head_sha(repo_root)

    result = maybe_run_agent(
        agent=agent,
        model=model,
        effort=effort,
        prompt=prompt,
        repo_root=repo_root,
        stdout_path=phase_dir / "agent.stdout.log",
        stderr_path=phase_dir / "agent.stderr.log",
        last_message_path=(
            phase_dir / "agent-last-message.md" if agent == "codex" else None
        ),
        mirror_to_terminal=False,
        timeout=timeout,
    )

    if result.returncode != 0:
        revert_to(repo_root, head_before)
        return ExecutePhaseOutcome(
            status="failed",
            reason=f"Agent failed with exit code {result.returncode}",
        )

    test_result = run_tests(
        artifacts.test_command,
        repo_root,
        stdout_path=phase_dir / "tests.stdout.log",
        stderr_path=phase_dir / "tests.stderr.log",
        mirror_to_terminal=False,
    )

    if test_result.returncode != 0:
        revert_to(repo_root, head_before)
        return ExecutePhaseOutcome(
            status="failed",
            reason=f"Tests failed: {summarize_output(test_result)}",
        )

    phase_index = _find_phase_index(manifest, phase)
    updated_phases = tuple(
        replace(p, done=True) if i == phase_index else p
        for i, p in enumerate(manifest.phases)
    )
    now = iso_timestamp()
    updated_manifest = replace(manifest, phases=updated_phases, last_touch=now)
    if phase_index == manifest.current_phase:
        updated_manifest = replace(
            updated_manifest, current_phase=manifest.current_phase + 1,
        )

    manifest_path = migration_root(live_dir, manifest.name) / "manifest.json"
    save_manifest(updated_manifest, manifest_path)

    return ExecutePhaseOutcome(status="done", reason="Phase completed successfully")
