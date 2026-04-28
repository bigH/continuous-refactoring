from __future__ import annotations

from pathlib import Path

from continuous_refactoring.commit_messages import (
    build_commit_message,
    commit_rationale,
)
from continuous_refactoring.decisions import AgentStatus


def test_build_commit_message_includes_why_and_validation() -> None:
    message = build_commit_message(
        "continuous refactor: src/example.py",
        why="Remove duplicated parsing so future changes touch one branch.",
        validation="uv run pytest",
    )

    assert message == (
        "continuous refactor: src/example.py\n"
        "\n"
        "Why:\n"
        "Remove duplicated parsing so future changes touch one branch.\n"
        "\n"
        "Validation:\n"
        "uv run pytest"
    )


def test_commit_rationale_prefers_explicit_status_rationale() -> None:
    rationale = commit_rationale(
        AgentStatus(
            summary="Ready to commit.",
            commit_rationale="Make retry behavior explainable from one helper.",
        ),
        fallback="fallback",
        repo_root=Path("/repo"),
    )

    assert rationale == "Make retry behavior explainable from one helper."


def test_commit_rationale_uses_summary_before_fallback() -> None:
    rationale = commit_rationale(
        AgentStatus(summary="Collapse duplicated validation branches."),
        fallback="fallback",
        repo_root=Path("/repo"),
    )

    assert rationale == "Collapse duplicated validation branches."


def test_commit_rationale_ignores_placeholder_summary() -> None:
    rationale = commit_rationale(
        AgentStatus(summary="Ready to commit."),
        fallback="agent stdout explained the cleanup",
        repo_root=Path("/repo"),
    )

    assert rationale == "agent stdout explained the cleanup"
