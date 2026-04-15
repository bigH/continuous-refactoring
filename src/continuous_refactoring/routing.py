from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Literal

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


def _parse_decision(stdout: str) -> ClassifierDecision:
    last_output_line: str | None = None
    for line in reversed(stdout.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        last_output_line = stripped
        match = _DECISION_RE.match(stripped)
        if match:
            match_text = match.group(1).lower()
            if match_text == "cohesive-cleanup":
                return "cohesive-cleanup"
            return "needs-plan"
    if last_output_line is None:
        raise ContinuousRefactorError("Classifier produced no output")
    raise ContinuousRefactorError(
        f"Classifier produced unrecognised output: {last_output_line!r}"
    )


def classify_target(
    target: Target,
    taste: str,
    repo_root: Path,
    artifacts: RunArtifacts,
    *,
    agent: str,
    model: str,
    effort: str,
    timeout: int | None,
) -> ClassifierDecision:
    prompt = compose_classifier_prompt(target, taste)
    classify_dir = artifacts.root / "classify"
    classify_dir.mkdir(parents=True, exist_ok=True)

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

    if result.returncode != 0:
        raise ContinuousRefactorError(
            f"Classifier agent failed with exit code {result.returncode}"
        )

    return _parse_decision(result.stdout)
