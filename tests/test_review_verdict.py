from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from continuous_refactoring.artifacts import CommandCapture

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_larger_refactorings_plan.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("_rlrp", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_rlrp"] = module
    spec.loader.exec_module(module)
    return module


rlrp = _load_script_module()


def _capture(stdout: str = "", stderr: str = "") -> CommandCapture:
    return CommandCapture(
        command=("fake",),
        returncode=0,
        stdout=stdout,
        stderr=stderr,
        stdout_path=Path("/dev/null"),
        stderr_path=Path("/dev/null"),
    )


def _claude_result_line(final_message: str, *, timestamp_prefix: bool = True) -> str:
    event = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": final_message,
        "stop_reason": "end_turn",
    }
    line = json.dumps(event, separators=(",", ":"))
    return f"[2026-04-14T00:04:03.441-07:00] {line}" if timestamp_prefix else line


def test_claude_stream_json_with_review_ok_at_end_of_result() -> None:
    final = "Criteria checklist:\n1. foo ok\n2. bar ok\n\nREVIEW_OK"
    stdout = (
        '[2026-04-14T00:03:17.474-07:00] {"type":"stream_event","event":{"type":"x"}}\n'
        + _claude_result_line(final)
        + "\n"
    )
    ok, reason = rlrp._review_verdict(_capture(stdout=stdout))
    assert ok is True
    assert reason == ""


def test_claude_stream_json_with_review_failed() -> None:
    final = "Something went wrong.\nREVIEW_FAILED: missing test for unknown status"
    stdout = _claude_result_line(final) + "\n"
    ok, reason = rlrp._review_verdict(_capture(stdout=stdout))
    assert ok is False
    assert reason == "missing test for unknown status"


def test_claude_stream_json_with_result_type_after_other_fields() -> None:
    event = json.dumps(
        {
            "subtype": "success",
            "is_error": False,
            "result": "REVIEW_OK",
            "type": "result",
        },
        separators=(",", ":"),
    )
    stdout = f"[2026-04-14T00:04:03.441-07:00] {event}\n"
    ok, reason = rlrp._review_verdict(_capture(stdout=stdout))
    assert ok is True
    assert reason == ""


def test_claude_stream_json_without_timestamp_prefix() -> None:
    final = "All good.\nREVIEW_OK"
    stdout = _claude_result_line(final, timestamp_prefix=False) + "\n"
    ok, reason = rlrp._review_verdict(_capture(stdout=stdout))
    assert ok is True


def test_plain_text_review_ok_still_works() -> None:
    stdout = "some output\nREVIEW_OK\n"
    ok, reason = rlrp._review_verdict(_capture(stdout=stdout))
    assert ok is True
    assert reason == ""


def test_plain_text_review_failed_still_works() -> None:
    stdout = "diff looks wrong\nREVIEW_FAILED: criterion 3 not met\n"
    ok, reason = rlrp._review_verdict(_capture(stdout=stdout))
    assert ok is False
    assert reason == "criterion 3 not met"


def test_json_result_preempts_plain_text_sentinel() -> None:
    stdout = _claude_result_line("REVIEW_FAILED: stale review") + "\nREVIEW_OK\n"
    ok, reason = rlrp._review_verdict(_capture(stdout=stdout))
    assert ok is False
    assert reason == "stale review"


def test_missing_sentinel_returns_false() -> None:
    stdout = _claude_result_line("I am done but forgot the sentinel.") + "\n"
    ok, reason = rlrp._review_verdict(_capture(stdout=stdout))
    assert ok is False
    assert "REVIEW_OK" in reason


def test_last_message_path_takes_precedence(tmp_path: Path) -> None:
    last = tmp_path / "agent-last-message.md"
    last.write_text("ok from codex\nREVIEW_OK\n", encoding="utf-8")
    # stdout says FAILED -- we expect last-message (codex) path to win.
    stdout = _claude_result_line("REVIEW_FAILED: stale") + "\n"
    ok, _ = rlrp._review_verdict(_capture(stdout=stdout), last_message_path=last)
    assert ok is True


def test_trailing_banners_after_sentinel_ignored() -> None:
    final = "REVIEW_OK"
    stdout = (
        _claude_result_line(final)
        + "\n"
        + '[2026-04-14T00:04:04.000-07:00] {"type":"system","subtype":"tokens_used"}\n'
    )
    ok, _ = rlrp._review_verdict(_capture(stdout=stdout))
    assert ok is True


def test_sentinel_survives_banner_inside_result_field() -> None:
    """Scanner walks reverse and skips non-sentinel lines, so a short banner
    appended after REVIEW_OK inside the result text still resolves to OK."""
    final = "REVIEW_OK\nsession complete"
    stdout = _claude_result_line(final) + "\n"
    ok, _ = rlrp._review_verdict(_capture(stdout=stdout))
    assert ok is True


def test_stderr_scan_falls_back_when_stdout_lacks_sentinel() -> None:
    stdout = "noise with no sentinel\n"
    stderr = "REVIEW_FAILED: tests red\n"
    ok, reason = rlrp._review_verdict(_capture(stdout=stdout, stderr=stderr))
    assert ok is False
    assert reason == "tests red"


def test_parse_plan_status_understands_prefixed_states() -> None:
    assert rlrp.parse_plan_status("todo") is rlrp.PlanStatus.TODO
    assert rlrp.parse_plan_status("TODO") is rlrp.PlanStatus.TODO
    assert rlrp.parse_plan_status("awaiting human review") is rlrp.PlanStatus.AWAITING
    assert (
        rlrp.parse_plan_status("failed -- incompatible task state")
        is rlrp.PlanStatus.FAILED
    )


def test_parse_plan_status_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unrecognized plan status"):
        rlrp.parse_plan_status("stalled")
