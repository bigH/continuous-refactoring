from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from continuous_refactoring.artifacts import RunArtifacts
    from continuous_refactoring.targeting import Target

__all__ = [
    "ScopeSelection",
    "describe_scope_candidate",
    "parse_scope_selection",
    "scope_candidate_to_target",
    "scope_expansion_bypass_reason",
    "select_scope_candidate",
    "write_scope_expansion_artifacts",
]

from continuous_refactoring.agent import maybe_run_agent
from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.prompts import (
    compose_scope_selection_prompt,
    scope_candidate_detail_lines,
)
from continuous_refactoring.scope_candidates import (
    ScopeCandidate,
    ScopeCandidateKind,
    build_scope_candidates,
)

_SELECTION_RE = re.compile(
    r"^selected-candidate:\s*(seed|local-cluster|cross-cluster)"
    r"(?:\s*[—-]\s*(.+))?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ScopeSelection:
    kind: ScopeCandidateKind
    reason: str


def _scope_selection_line(selection: ScopeSelection) -> str:
    return f"selected-candidate: {selection.kind} — {selection.reason}\n"


def _write_selection_logs(selection_dir: Path, selection: ScopeSelection) -> None:
    line = _scope_selection_line(selection)
    (selection_dir / "selection.stdout.log").write_text(line, encoding="utf-8")
    (selection_dir / "selection-last-message.md").write_text(line, encoding="utf-8")


def scope_expansion_bypass_reason(target: Target) -> str | None:
    if len(target.files) == 0:
        return "scope expansion requires a seed file"
    if len(target.files) > 1 and target.provenance in {"paths", "targets"}:
        return "scope expansion bypassed for explicit multi-file target"
    if len(target.files) != 1:
        return "scope expansion requires a single seed file"
    return None


def parse_scope_selection(
    stdout: str,
    candidate_kinds: tuple[ScopeCandidateKind, ...],
) -> ScopeSelection:
    non_blank = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not non_blank:
        raise ContinuousRefactorError("Scope selection produced no output")
    for stripped in reversed(non_blank):
        match = _SELECTION_RE.match(stripped)
        if not match:
            continue
        kind = match.group(1).lower()
        if kind not in candidate_kinds:
            raise ContinuousRefactorError(
                f"Selection chose unavailable candidate: {kind!r}"
            )
        reason = match.group(2).strip() if match.group(2) else kind
        return ScopeSelection(kind=kind, reason=reason)
    raise ContinuousRefactorError(
        f"Scope selection produced unrecognised output: {non_blank[-1]!r}"
    )


def scope_candidate_to_target(target: Target, candidate: ScopeCandidate) -> Target:
    return replace(target, files=candidate.files)


def describe_scope_candidate(candidate: ScopeCandidate) -> str:
    header = f"Selected scope candidate: {candidate.kind}"
    return "\n".join([header, *scope_candidate_detail_lines(candidate)])


def select_scope_candidate(
    target: Target,
    candidates: tuple[ScopeCandidate, ...],
    taste: str,
    repo_root: Path,
    artifacts: RunArtifacts,
    *,
    agent: str,
    model: str,
    effort: str,
    timeout: int | None,
    effort_metadata: dict[str, object] | None = None,
) -> ScopeSelection:
    selection_dir = artifacts.root / "scope-expansion"
    selection_dir.mkdir(parents=True, exist_ok=True)
    selection_stdout_path = selection_dir / "selection.stdout.log"
    selection_last_message_path = selection_dir / "selection-last-message.md"

    if len(candidates) == 1:
        selection = ScopeSelection(
            kind=candidates[0].kind,
            reason="only viable candidate",
        )
        _write_selection_logs(selection_dir, selection)
        return selection

    result = maybe_run_agent(
        agent=agent,
        model=model,
        effort=effort,
        prompt=compose_scope_selection_prompt(target, candidates, taste),
        repo_root=repo_root,
        stdout_path=selection_stdout_path,
        stderr_path=selection_dir / "selection.stderr.log",
        last_message_path=selection_last_message_path if agent == "codex" else None,
        mirror_to_terminal=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise ContinuousRefactorError(
            f"Scope selection agent failed with exit code {result.returncode}"
        )
    candidate_kinds = tuple(candidate.kind for candidate in candidates)
    return parse_scope_selection(result.stdout, candidate_kinds)


def write_scope_expansion_artifacts(
    scope_dir: Path,
    target: Target,
    candidates: tuple[ScopeCandidate, ...],
    *,
    bypass_reason: str | None = None,
    selection: ScopeSelection | None = None,
) -> None:
    scope_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "target": {
            "description": target.description,
            "files": list(target.files),
            "provenance": target.provenance,
        },
        "bypass_reason": bypass_reason,
        "candidates": [asdict(candidate) for candidate in candidates],
    }
    if selection is not None:
        payload["selection"] = asdict(selection)
    (scope_dir / "variants.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
