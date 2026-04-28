from __future__ import annotations

from pathlib import Path

from continuous_refactoring.decisions import AgentStatus, sanitize_text

__all__ = [
    "build_commit_message",
    "commit_rationale",
]

_EMPTY_VALUES = frozenset({"none", "n/a", "na"})
_PLACEHOLDER_SUMMARIES = frozenset(
    {
        "ready to commit",
        "validated refactor ready to commit",
    }
)


def _normalized_value(text: str) -> str:
    return text.lower().rstrip(".")


def _present_text(text: str | None) -> str | None:
    if text is None:
        return None
    stripped = text.strip()
    if not stripped or _normalized_value(stripped) in _EMPTY_VALUES:
        return None
    return stripped


def commit_rationale(
    status: AgentStatus | None,
    *,
    fallback: str,
    repo_root: Path,
) -> str:
    if status is not None:
        rationale = _present_text(sanitize_text(status.commit_rationale, repo_root))
        if rationale is not None:
            return rationale

        summary = _present_text(sanitize_text(status.summary, repo_root))
        if (
            summary is not None
            and _normalized_value(summary) not in _PLACEHOLDER_SUMMARIES
        ):
            return summary

    fallback_text = _present_text(sanitize_text(fallback, repo_root))
    if fallback_text is not None:
        return fallback_text
    return "Validated cleanup completed."


def build_commit_message(
    subject: str,
    *,
    why: str,
    validation: str | None = None,
) -> str:
    sections = [f"Why:\n{why.strip()}"]
    validation_text = _present_text(validation)
    if validation_text is not None:
        sections.append(f"Validation:\n{validation_text}")
    return f"{subject.strip()}\n\n" + "\n\n".join(sections)
