from __future__ import annotations

import random
import string
from pathlib import Path
from typing import get_args

import pytest

from continuous_refactoring.decisions import (
    RetryRecommendation,
    RunnerDecision,
    error_failure_kind,
    parse_status_block,
    sanitize_text,
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
