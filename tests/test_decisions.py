from __future__ import annotations

import random
import string
from pathlib import Path
from typing import get_args

import pytest

from continuous_refactoring.decisions import (
    AgentStatus,
    RetryRecommendation,
    RunnerDecision,
    default_retry_recommendation,
    error_failure_kind,
    parse_status_block,
    read_status,
    resolved_phase_reached,
    sanitize_text,
    sanitized_text_or,
    status_summary,
)
from continuous_refactoring.prompts import (
    CONTINUOUS_REFACTORING_STATUS_BEGIN,
    CONTINUOUS_REFACTORING_STATUS_END,
)


def _status_block(body: str) -> str:
    return (
        f"{CONTINUOUS_REFACTORING_STATUS_BEGIN}\n"
        f"{body}\n"
        f"{CONTINUOUS_REFACTORING_STATUS_END}\n"
    )


def test_parse_status_block_parses_expected_fields() -> None:
    status = parse_status_block(
        _status_block(
            "\n".join(
                [
                    "phase_reached: refactor",
                    "decision: retry",
                    "retry_recommendation: same-target",
                    "failure_kind: validation-failed",
                    "summary: first",
                    "summary: last write wins",
                    "commit_rationale: remove duplicated parsing paths",
                    "next_retry_focus: rerun targeted tests",
                    "tests_run: uv run pytest -x",
                    "evidence: artifacts/summary.json",
                    "  - artifacts/events.jsonl",
                    "ignored text without colon",
                ],
            ),
        ),
    )

    assert status is not None
    assert status.phase_reached == "refactor"
    assert status.decision == "retry"
    assert status.retry_recommendation == "same-target"
    assert status.failure_kind == "validation-failed"
    assert status.summary == "last write wins"
    assert status.commit_rationale == "remove duplicated parsing paths"
    assert status.next_retry_focus == "rerun targeted tests"
    assert status.tests_run == "uv run pytest -x"
    assert status.evidence == (
        "artifacts/summary.json",
        "artifacts/events.jsonl",
    )


def test_parse_status_block_normalizes_invalid_enum_values() -> None:
    status = parse_status_block(
        _status_block(
            "\n".join(
                [
                    "phase_reached: refactor",
                    "decision: maybe",
                    "retry_recommendation: later",
                    "summary: keep parsing",
                ],
            ),
        ),
    )

    assert status is not None
    assert status.decision is None
    assert status.retry_recommendation is None
    assert status.summary == "keep parsing"


@pytest.mark.parametrize("decision", get_args(RunnerDecision))
def test_parse_status_block_accepts_each_runner_decision(
    decision: RunnerDecision,
) -> None:
    status = parse_status_block(_status_block(f"decision: {decision}"))

    assert status is not None
    assert status.decision == decision


@pytest.mark.parametrize("retry_recommendation", get_args(RetryRecommendation))
def test_parse_status_block_accepts_each_retry_recommendation(
    retry_recommendation: RetryRecommendation,
) -> None:
    status = parse_status_block(
        _status_block(f"retry_recommendation: {retry_recommendation}"),
    )

    assert status is not None
    assert status.retry_recommendation == retry_recommendation


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("plain text only", None),
        (CONTINUOUS_REFACTORING_STATUS_BEGIN, None),
        (_status_block(""), None),
        (
            _status_block("summary: valid first")
            + f"{CONTINUOUS_REFACTORING_STATUS_BEGIN}\nsummary: incomplete tail\n",
            None,
        ),
    ],
)
def test_parse_status_block_handles_missing_or_truncated_blocks(
    text: str, expected: object,
) -> None:
    assert parse_status_block(text) is expected


def test_parse_status_block_never_raises_on_generated_corpus() -> None:
    rng = random.Random(0)
    corpus = [
        "".join(rng.choice(string.printable) for _ in range(length))
        for length in range(80)
    ]
    corpus.extend(
        [
            _status_block("decision: retry\nretry_recommendation: none"),
            _status_block("evidence:\n- one\n- two"),
            f"{CONTINUOUS_REFACTORING_STATUS_BEGIN}\nsummary only",
            f"{CONTINUOUS_REFACTORING_STATUS_END}\nsummary: dangling end",
        ],
    )

    allowed_decisions = set(get_args(RunnerDecision)) | {None}
    allowed_retries = set(get_args(RetryRecommendation)) | {None}

    for text in corpus:
        status = parse_status_block(text)
        if status is None:
            continue
        assert status.decision in allowed_decisions
        assert status.retry_recommendation in allowed_retries
        assert isinstance(status.evidence, tuple)
        assert all(isinstance(item, str) for item in status.evidence)


def test_read_status_prefers_codex_last_message_file(tmp_path: Path) -> None:
    last_message_path = tmp_path / "codex-last-message.md"
    last_message_path.write_text(
        _status_block("summary: from file"),
        encoding="utf-8",
    )
    fallback = _status_block("summary: from fallback")

    codex_status = read_status(
        "codex",
        last_message_path=last_message_path,
        fallback_text=fallback,
    )
    other_status = read_status(
        "claude",
        last_message_path=last_message_path,
        fallback_text=fallback,
    )

    assert codex_status is not None
    assert codex_status.summary == "from file"
    assert other_status is not None
    assert other_status.summary == "from fallback"


def test_sanitize_text_filters_and_redacts() -> None:
    repo_root = Path("/worktree/repo")
    text = "\n".join(
        [
            "",
            "  codex exec --dangerous ",
            f" touched {repo_root}/src/continuous_refactoring/loop.py ",
            " tmp log: /tmp/run-123/output.txt ",
            " extra   spacing ",
        ],
    )

    sanitized = sanitize_text(text, repo_root)

    assert sanitized == (
        "touched <repo>/src/continuous_refactoring/loop.py "
        "tmp log: <tmp> extra spacing"
    )
    assert "codex exec" not in sanitized
    repo_bound = len(text.replace(str(repo_root), "<repo>"))
    assert len(sanitized) <= min(240, repo_bound)


@pytest.mark.parametrize("text", [None, "", "   \n", "codex exec --help"])
def test_sanitize_text_returns_none_for_empty_or_filtered_input(
    text: str | None,
) -> None:
    assert sanitize_text(text, Path("/repo")) is None


def test_sanitize_text_is_idempotent() -> None:
    repo_root = Path("/repo")
    once = sanitize_text(
        " line one \n /tmp/demo/artifact.log \n line two ",
        repo_root,
    )

    assert once is not None
    assert sanitize_text(once, repo_root) == once


def test_sanitized_text_or_prefers_sanitized_text() -> None:
    repo_root = Path("/repo")

    assert (
        sanitized_text_or(" touched /repo/src/file.py ", repo_root, "fallback")
        == "touched <repo>/src/file.py"
    )


def test_sanitized_text_or_uses_fallback_when_sanitized_text_is_empty() -> None:
    assert (
        sanitized_text_or("codex exec --help", Path("/repo"), "fallback")
        == "fallback"
    )


def test_status_summary_sanitizes_summary_and_focus() -> None:
    status = AgentStatus(
        summary=" touched /repo/src/file.py ",
        next_retry_focus=" /tmp/logs/run.txt ",
    )

    assert status_summary(status, fallback="fallback", repo_root=Path("/repo")) == (
        "touched <repo>/src/file.py",
        "<tmp>",
    )


def test_resolved_phase_reached_uses_fallback_for_missing_status_or_phase() -> None:
    fallback = "review"

    assert resolved_phase_reached(None, fallback) == fallback
    assert resolved_phase_reached(AgentStatus(), fallback) == fallback
    assert resolved_phase_reached(AgentStatus(phase_reached="refactor"), fallback) == (
        "refactor"
    )


@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        ("commit", "none"),
        ("retry", "same-target"),
        ("abandon", "new-target"),
        ("blocked", "human-review"),
    ],
)
def test_default_retry_recommendation_maps_each_decision(
    decision: RunnerDecision,
    expected: RetryRecommendation,
) -> None:
    assert default_retry_recommendation(decision) == expected


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Agent timed out after 5m", "timeout"),
        ("agent produced no output before exit", "stuck"),
        (
            "agent timed out and then produced no output",
            "timeout",
        ),
        ("transport failed", "agent-infra-failure"),
    ],
)
def test_error_failure_kind_maps_expected_cases(
    message: str, expected: str,
) -> None:
    assert error_failure_kind(message) == expected


def test_error_failure_kind_is_total_over_generated_strings() -> None:
    rng = random.Random(0)
    allowed = {"timeout", "stuck", "agent-infra-failure"}

    for length in range(80):
        message = "".join(rng.choice(string.printable) for _ in range(length))
        assert error_failure_kind(message) in allowed
