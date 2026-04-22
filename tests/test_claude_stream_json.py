from __future__ import annotations

import json
import re
from pathlib import Path

from continuous_refactoring.agent import _extract_claude_final_text
from continuous_refactoring.phases import _parse_ready_verdict
from continuous_refactoring.planning import (
    _parse_final_decision,
    _review_has_findings,
)
from continuous_refactoring.routing import _parse_decision
from continuous_refactoring.scope_expansion import parse_scope_selection


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "claude_stream_json"
    / "selection.stdout.log"
)


def _as_line(event: dict[str, object]) -> str:
    return json.dumps(event)


def _stream(*events: dict[str, object]) -> str:
    return "\n".join(_as_line(event) for event in events) + "\n"


def _assistant_event(*texts: str) -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": text} for text in texts],
        },
    }


def _result_event(
    result: object,
    *,
    is_error: bool = False,
    subtype: str = "success",
) -> dict[str, object]:
    return {
        "type": "result",
        "subtype": subtype,
        "is_error": is_error,
        "result": result,
    }


# ---------------------------------------------------------------------------
# Unit tests for _extract_claude_final_text
# ---------------------------------------------------------------------------


def test_returns_result_event_value_when_present() -> None:
    stream = _stream(
        {"type": "system", "subtype": "init"},
        _assistant_event("partial draft"),
        _result_event("selected-candidate: seed — final answer"),
    )

    assert (
        _extract_claude_final_text(stream)
        == "selected-candidate: seed — final answer"
    )


def test_result_is_error_true_falls_back_to_assistant_parts() -> None:
    stream = _stream(
        _assistant_event("selected-candidate: local-cluster"),
        _result_event("error payload", is_error=True, subtype="error_max_turns"),
    )

    assert (
        _extract_claude_final_text(stream) == "selected-candidate: local-cluster"
    )


def test_result_missing_field_falls_back_to_assistant_parts() -> None:
    stream = _stream(
        _assistant_event("fallback body"),
        {"type": "result", "subtype": "success", "is_error": False},
    )

    assert _extract_claude_final_text(stream) == "fallback body"


def test_result_null_value_falls_back() -> None:
    stream = _stream(
        _assistant_event("assistant wins"),
        _result_event(None),
    )

    assert _extract_claude_final_text(stream) == "assistant wins"


def test_result_with_nested_object_falls_back() -> None:
    stream = _stream(
        _assistant_event("string wins over dict"),
        _result_event({"text": "not a top-level string"}),
    )

    assert _extract_claude_final_text(stream) == "string wins over dict"


def test_only_assistant_events_returns_joined_text() -> None:
    stream = _stream(_assistant_event("selected-candidate: seed"))

    assert _extract_claude_final_text(stream) == "selected-candidate: seed"


def test_multi_content_block_assistant_event_concatenates_blocks() -> None:
    stream = _stream(_assistant_event("selected-", "candidate: seed"))

    assert _extract_claude_final_text(stream) == "selected-candidate: seed"


def test_multiple_assistant_messages_join_with_newline() -> None:
    stream = _stream(
        _assistant_event("line one"),
        _assistant_event("line two"),
    )

    assert _extract_claude_final_text(stream) == "line one\nline two"


def test_assistant_content_skips_non_text_blocks() -> None:
    stream = _stream(
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}},
                    {"type": "text", "text": "only-the-text-block"},
                    {"type": "thinking", "thinking": "ignored"},
                ],
            },
        },
    )

    assert _extract_claude_final_text(stream) == "only-the-text-block"


def test_empty_input_returns_empty_string() -> None:
    assert _extract_claude_final_text("") == ""


def test_malformed_json_lines_are_skipped() -> None:
    good = _as_line(_result_event("final"))
    stream = "{not valid json\n" + good + "\nplain prose\n{\n"

    assert _extract_claude_final_text(stream) == "final"


def test_unknown_types_only_returns_raw() -> None:
    stream = _stream(
        {"type": "system", "subtype": "init"},
        {"type": "stream_event", "event": {"type": "message_start"}},
        {"type": "rate_limit_event"},
    )

    assert _extract_claude_final_text(stream) == stream


def test_content_block_delta_events_are_ignored() -> None:
    stream = _stream(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "partial"},
            },
        },
        _assistant_event("complete answer"),
    )

    assert _extract_claude_final_text(stream) == "complete answer"


def test_last_valid_result_wins_over_later_invalid_result() -> None:
    stream = _stream(
        _result_event("first valid"),
        _result_event(None),
        _result_event("", is_error=False),
        _result_event("error body", is_error=True),
    )

    assert _extract_claude_final_text(stream) == "first valid"


def test_later_valid_result_overrides_earlier_valid_result() -> None:
    stream = _stream(
        _result_event("earlier"),
        _result_event("later"),
    )

    assert _extract_claude_final_text(stream) == "later"


def test_assistant_message_with_string_content_skipped() -> None:
    # content must be a list; stringly-typed content should not crash or
    # contribute to output — falls back to raw.
    stream = _stream(
        {
            "type": "assistant",
            "message": {"role": "assistant", "content": "not-a-list"},
        },
    )

    assert _extract_claude_final_text(stream) == stream


def test_non_object_json_line_is_skipped() -> None:
    stream = "[1,2,3]\n" + _as_line(_result_event("value")) + "\n"

    assert _extract_claude_final_text(stream) == "value"


# ---------------------------------------------------------------------------
# Fixture-driven tests
# ---------------------------------------------------------------------------


_TIMESTAMP_PREFIX = re.compile(r"^\[\d{4}-\d{2}-\d{2}T[^\]]+\]\s+")


def _fixture_as_in_memory_stdout() -> str:
    """Replay the on-disk artifact into the form ``CommandCapture.stdout`` holds.

    ``run_observed_command`` only prefixes ``[timestamp] `` when writing to the
    file sink; the in-memory ``stdout`` string is raw NDJSON. Strip the prefix
    so the extractor sees what it would see in production.
    """
    raw = FIXTURE_PATH.read_text(encoding="utf-8")
    return "".join(
        _TIMESTAMP_PREFIX.sub("", line) for line in raw.splitlines(keepends=True)
    )


def test_fixture_extractor_yields_selected_candidate_line() -> None:
    extracted = _extract_claude_final_text(_fixture_as_in_memory_stdout())

    assert "selected-candidate:" in extracted


def test_fixture_extraction_is_accepted_by_parse_scope_selection() -> None:
    extracted = _extract_claude_final_text(_fixture_as_in_memory_stdout())

    selection = parse_scope_selection(
        extracted, ("seed", "local-cluster", "cross-cluster"),
    )

    assert selection.kind == "seed"


# ---------------------------------------------------------------------------
# Round-trip tests for other parsers
# ---------------------------------------------------------------------------


def _synthetic_grammar_stream(grammar_text: str) -> str:
    """Build a realistic claude stream-json: init + assistant + mirrored result."""
    return _stream(
        {"type": "system", "subtype": "init"},
        _assistant_event(grammar_text),
        _result_event(grammar_text),
    )


def test_roundtrip_parse_decision_cohesive_cleanup() -> None:
    stream = _synthetic_grammar_stream("decision: cohesive-cleanup")

    assert _parse_decision(_extract_claude_final_text(stream)) == "cohesive-cleanup"


def test_roundtrip_parse_ready_verdict_yes_with_reason() -> None:
    stream = _synthetic_grammar_stream("ready: yes — all phases complete")

    verdict, reason = _parse_ready_verdict(_extract_claude_final_text(stream))

    assert verdict == "yes"
    assert reason == "all phases complete"


def test_roundtrip_parse_final_decision_approve_auto() -> None:
    stream = _synthetic_grammar_stream(
        "final-decision: approve-auto — plan is tight and reviewed",
    )

    decision, reason = _parse_final_decision(_extract_claude_final_text(stream))

    assert decision == "approve-auto"
    assert reason == "plan is tight and reviewed"


def test_roundtrip_review_has_findings_no_findings_case() -> None:
    stream = _synthetic_grammar_stream("no findings")

    assert _review_has_findings(_extract_claude_final_text(stream)) is False


def test_roundtrip_review_has_findings_has_findings_case() -> None:
    stream = _synthetic_grammar_stream(
        "- finding: phase 2 precondition is ambiguous\n"
        "- finding: missing rollback step in phase 3",
    )

    assert _review_has_findings(_extract_claude_final_text(stream)) is True
