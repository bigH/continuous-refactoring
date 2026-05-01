from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from continuous_refactoring.artifacts import RunArtifacts
    from continuous_refactoring.targeting import Target

__all__ = [
    "ScopeSelection",
    "parse_scope_selection",
    "scope_candidate_to_target",
    "scope_expansion_bypass_reason",
    "select_scope_candidate",
    "write_scope_expansion_artifacts",
]

from continuous_refactoring.agent import maybe_run_agent
from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.prompts import compose_scope_selection_prompt
from continuous_refactoring.scope_candidates import ScopeCandidate, ScopeCandidateKind

_SCOPE_SELECTION_PREFIX = "selected-candidate:"
_KNOWN_SCOPE_SELECTION_KINDS: tuple[ScopeCandidateKind, ...] = (
    "local-cluster",
    "cross-cluster",
    "seed",
)


@dataclass(frozen=True)
class ScopeSelection:
    kind: ScopeCandidateKind
    reason: str


def _scope_selection_line(selection: ScopeSelection) -> str:
    return f"selected-candidate: {selection.kind} — {selection.reason}\n"


def write_scope_selection_logs(selection_dir: Path, selection: ScopeSelection) -> None:
    line = _scope_selection_line(selection)
    (selection_dir / "selection.stdout.log").write_text(line, encoding="utf-8")
    (selection_dir / "selection-last-message.md").write_text(line, encoding="utf-8")


def _parse_selection_line(line: str) -> tuple[ScopeCandidateKind, str] | None:
    if not line[: len(_SCOPE_SELECTION_PREFIX)].lower() == _SCOPE_SELECTION_PREFIX:
        return None
    body = line[len(_SCOPE_SELECTION_PREFIX):].strip()
    for kind in _KNOWN_SCOPE_SELECTION_KINDS:
        if not body.lower().startswith(kind):
            continue
        reason = body[len(kind):].strip()
        if not reason:
            return kind, kind
        if reason[0] not in {"—", "-"}:
            return None
        reason = reason[1:].strip()
        return kind, reason or kind
    return None


def _require_unique_candidate_kinds(
    candidate_kinds: tuple[ScopeCandidateKind, ...],
) -> tuple[ScopeCandidateKind, ...]:
    duplicates = tuple(
        kind for kind in _KNOWN_SCOPE_SELECTION_KINDS if candidate_kinds.count(kind) > 1
    )
    if duplicates:
        quoted = ", ".join(repr(kind) for kind in duplicates)
        raise ContinuousRefactorError(
            f"Scope selection requires unique candidate kinds, got duplicates: {quoted}"
        )
    return candidate_kinds


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
    candidate_kinds = _require_unique_candidate_kinds(candidate_kinds)
    non_blank = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not non_blank:
        raise ContinuousRefactorError("Scope selection produced no output")
    for stripped in reversed(non_blank):
        parsed = _parse_selection_line(stripped)
        if parsed is None:
            continue
        kind, reason = parsed
        if kind not in candidate_kinds:
            raise ContinuousRefactorError(
                f"Selection chose unavailable candidate: {kind!r}"
            )
        return ScopeSelection(kind=kind, reason=reason)
    raise ContinuousRefactorError(
        f"Scope selection produced unrecognised output: {non_blank[-1]!r}"
    )


def scope_candidate_to_target(target: Target, candidate: ScopeCandidate) -> Target:
    return replace(target, files=candidate.files)


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
    attempt: int = 1,
    retry: int = 1,
    effort_metadata: dict[str, object] | None = None,
) -> ScopeSelection:
    candidate_kinds = _require_unique_candidate_kinds(
        tuple(candidate.kind for candidate in candidates)
    )
    selection_dir = artifacts.root / "scope-expansion"
    selection_dir.mkdir(parents=True, exist_ok=True)
    selection_stdout_path = selection_dir / "selection.stdout.log"
    selection_last_message_path = selection_dir / "selection-last-message.md"

    if len(candidates) == 1:
        selection = ScopeSelection(
            kind=candidates[0].kind,
            reason="only viable candidate",
        )
        write_scope_selection_logs(selection_dir, selection)
        return selection

    call_role = "scope-expansion"
    artifacts.log_call_started(
        attempt=attempt,
        retry=retry,
        target=target.description,
        call_role=call_role,
        effort=effort_metadata,
    )

    try:
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
    except ContinuousRefactorError as error:
        artifacts.log_call_finished(
            attempt=attempt,
            retry=retry,
            target=target.description,
            call_role=call_role,
            status="failed",
            level="WARN",
            summary=str(error),
            effort=effort_metadata,
        )
        raise

    if result.returncode != 0:
        artifacts.log_call_finished(
            attempt=attempt,
            retry=retry,
            target=target.description,
            call_role=call_role,
            status="failed",
            level="WARN",
            returncode=result.returncode,
            summary=f"{agent} exited with code {result.returncode}",
            effort=effort_metadata,
        )
        raise ContinuousRefactorError(
            f"Scope selection agent failed with exit code {result.returncode}"
        )
    try:
        selection = parse_scope_selection(result.stdout, candidate_kinds)
    except ContinuousRefactorError as error:
        artifacts.log_call_finished(
            attempt=attempt,
            retry=retry,
            target=target.description,
            call_role=call_role,
            status="failed",
            level="WARN",
            returncode=result.returncode,
            summary=str(error),
            effort=effort_metadata,
        )
        raise

    artifacts.log_call_finished(
        attempt=attempt,
        retry=retry,
        target=target.description,
        call_role=call_role,
        status="finished",
        returncode=result.returncode,
        effort=effort_metadata,
    )
    return selection


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
