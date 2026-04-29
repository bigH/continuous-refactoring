from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

if TYPE_CHECKING:
    from continuous_refactoring.artifacts import RunArtifacts
    from continuous_refactoring.targeting import Target

__all__ = ["ClassifierDecision", "classify_target"]

from continuous_refactoring.agent import maybe_run_agent
from continuous_refactoring.artifacts import ContinuousRefactorError
from continuous_refactoring.prompts import compose_classifier_prompt

ClassifierDecision = Literal["cohesive-cleanup", "needs-plan"]

_DECISION_RE = re.compile(
    r"^decision:\s*(cohesive-cleanup|needs-plan)\b", re.IGNORECASE,
)


def _log_failed_classification(
    artifacts: RunArtifacts,
    target: Target,
    *,
    attempt: int,
    retry: int,
    summary: str,
    effort_metadata: dict[str, object] | None,
    returncode: int | None = None,
) -> None:
    artifacts.log_call_finished(
        attempt=attempt,
        retry=retry,
        target=target.description,
        call_role="classify",
        status="failed",
        level="WARN",
        returncode=returncode,
        summary=summary,
        effort=effort_metadata,
    )


def _parse_decision(stdout: str) -> ClassifierDecision:
    non_empty = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not non_empty:
        raise ContinuousRefactorError("Classifier produced no output")
    for line in reversed(non_empty):
        match = _DECISION_RE.match(line)
        if match:
            return cast(ClassifierDecision, match.group(1).lower())
    raise ContinuousRefactorError(
        f"Classifier produced unrecognised output: {non_empty[-1]!r}"
    )


def classify_target(
    target: Target,
    taste: str,
    repo_root: Path,
    artifacts: RunArtifacts,
    *,
    attempt: int = 1,
    retry: int = 1,
    agent: str,
    model: str,
    effort: str,
    timeout: int | None,
    effort_metadata: dict[str, object] | None = None,
) -> ClassifierDecision:
    prompt = compose_classifier_prompt(target, taste)
    classify_dir = artifacts.root / "classify"
    classify_dir.mkdir(parents=True, exist_ok=True)
    call_role = "classify"

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
            prompt=prompt,
            repo_root=repo_root,
            stdout_path=classify_dir / "agent.stdout.log",
            stderr_path=classify_dir / "agent.stderr.log",
            last_message_path=(
                classify_dir / "agent-last-message.md" if agent == "codex" else None
            ),
            mirror_to_terminal=False,
            timeout=timeout,
        )
    except ContinuousRefactorError as error:
        _log_failed_classification(
            artifacts,
            target,
            attempt=attempt,
            retry=retry,
            summary=str(error),
            effort_metadata=effort_metadata,
        )
        raise

    if result.returncode != 0:
        _log_failed_classification(
            artifacts,
            target,
            attempt=attempt,
            retry=retry,
            summary=f"{agent} exited with code {result.returncode}",
            effort_metadata=effort_metadata,
            returncode=result.returncode,
        )
        raise ContinuousRefactorError(
            f"Classifier agent failed with exit code {result.returncode}"
        )

    try:
        decision = _parse_decision(result.stdout)
    except ContinuousRefactorError as error:
        _log_failed_classification(
            artifacts,
            target,
            attempt=attempt,
            retry=retry,
            summary=str(error),
            effort_metadata=effort_metadata,
            returncode=result.returncode,
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
    return decision
