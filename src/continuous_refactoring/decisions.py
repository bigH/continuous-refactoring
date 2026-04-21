"""Agent status types and decision records."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from continuous_refactoring.prompts import (
    CONTINUOUS_REFACTORING_STATUS_BEGIN,
    CONTINUOUS_REFACTORING_STATUS_END,
)

__all__ = [
    "AgentStatus",
    "DecisionRecord",
    "RouteOutcome",
    "RunnerDecision",
    "RetryRecommendation",
    "default_retry_recommendation",
    "error_failure_kind",
    "parse_status_block",
    "read_status",
    "resolved_phase_reached",
    "sanitize_text",
    "status_summary",
]


RunnerDecision = Literal["commit", "retry", "abandon", "blocked"]
RetryRecommendation = Literal["same-target", "new-target", "none", "human-review"]
RouteOutcome = Literal["not-routed", "commit", "abandon", "blocked"]

_VALID_DECISIONS = frozenset({
    "commit",
    "retry",
    "abandon",
    "blocked",
    None,
})
_VALID_RETRY_RECOMMENDATIONS = frozenset({
    "same-target",
    "new-target",
    "none",
    "human-review",
    None,
})


@dataclass(frozen=True)
class AgentStatus:
    phase_reached: str | None = None
    decision: RunnerDecision | None = None
    retry_recommendation: RetryRecommendation | None = None
    failure_kind: str | None = None
    summary: str | None = None
    next_retry_focus: str | None = None
    tests_run: str | None = None
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionRecord:
    decision: RunnerDecision
    retry_recommendation: RetryRecommendation
    target: str
    call_role: str
    phase_reached: str
    failure_kind: str
    summary: str
    next_retry_focus: str | None = None
    retry_used: int = 1
    agent_last_message_path: Path | None = None
    agent_stdout_path: Path | None = None
    agent_stderr_path: Path | None = None
    tests_stdout_path: Path | None = None
    tests_stderr_path: Path | None = None


def _status_path_text(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def parse_status_block(text: str | None) -> AgentStatus | None:
    if not text:
        return None
    begin = text.rfind(CONTINUOUS_REFACTORING_STATUS_BEGIN)
    if begin < 0:
        return None
    end = text.find(CONTINUOUS_REFACTORING_STATUS_END, begin)
    if end < 0:
        return None
    block = text[begin + len(CONTINUOUS_REFACTORING_STATUS_BEGIN):end].strip()
    if not block:
        return None

    data: dict[str, str] = {}
    evidence: list[str] = []
    current_key: str | None = None
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if current_key == "evidence" and line.startswith("- "):
            evidence.append(line[2:].strip())
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        current_key = key.strip()
        if current_key == "evidence":
            if value.strip():
                evidence.append(value.strip())
            continue
        data[current_key] = value.strip()

    decision = data.get("decision", "").lower() or None
    if decision not in _VALID_DECISIONS:
        decision = None
    retry_recommendation = data.get("retry_recommendation", "").lower() or None
    if retry_recommendation not in _VALID_RETRY_RECOMMENDATIONS:
        retry_recommendation = None

    return AgentStatus(
        phase_reached=data.get("phase_reached") or None,
        decision=decision,
        retry_recommendation=retry_recommendation,
        failure_kind=data.get("failure_kind") or None,
        summary=data.get("summary") or None,
        next_retry_focus=data.get("next_retry_focus") or None,
        tests_run=data.get("tests_run") or None,
        evidence=tuple(evidence),
    )


def read_status(
    agent: str,
    *,
    last_message_path: Path | None,
    fallback_text: str | None,
) -> AgentStatus | None:
    if agent == "codex":
        status = parse_status_block(_status_path_text(last_message_path))
        if status is not None:
            return status
    return parse_status_block(fallback_text)


def sanitize_text(text: str | None, repo_root: Path) -> str | None:
    if not text:
        return None
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "codex exec" in line:
            continue
        line = line.replace(str(repo_root), "<repo>")
        line = re.sub(r"/tmp/[^ ]+", "<tmp>", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    if not lines:
        return None
    return " ".join(lines)[:240]


def status_summary(
    status: AgentStatus | None,
    *,
    fallback: str,
    repo_root: Path,
) -> tuple[str, str | None]:
    summary = sanitize_text(status.summary if status else None, repo_root) or fallback
    focus = sanitize_text(status.next_retry_focus if status else None, repo_root)
    return summary, focus


def resolved_phase_reached(status: AgentStatus | None, fallback: str) -> str:
    if status is None:
        return fallback
    return status.phase_reached or fallback


def error_failure_kind(message: str) -> str:
    lowered = message.lower()
    if "timed out" in lowered:
        return "timeout"
    if "produced no output" in lowered:
        return "stuck"
    return "agent-infra-failure"


def default_retry_recommendation(
    decision: RunnerDecision,
) -> RetryRecommendation:
    if decision == "retry":
        return "same-target"
    if decision == "abandon":
        return "new-target"
    if decision == "blocked":
        return "human-review"
    return "none"
