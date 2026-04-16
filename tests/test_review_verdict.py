from __future__ import annotations

import importlib.util
import json
import subprocess
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


def _plan_text(*task_bodies: str, status: str = "todo") -> str:
    blocks = "\n\n".join(
        f"```json task\n{body}\n```" for body in task_bodies
    )
    return (
        "# Larger refactorings\n"
        f"Status: {status}\n\n"
        f"{blocks}\n"
    )


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _init_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    _git(repo_root, "init", "-b", "main")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test User")


def _seed_recovery_repo(repo_root: Path) -> tuple[Path, str]:
    _init_repo(repo_root)
    plan_path = repo_root / "docs" / "plans" / "larger-refactorings.md"
    module_path = repo_root / "src" / "module.py"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.parent.mkdir(parents=True, exist_ok=True)

    head_plan_text = _plan_text(
        '{"id":"one","title":"First","type":"cleanup","touches":["src/module.py"],'
        '"blocked_by":[],"review_criteria":[],"done":false}',
        '{"id":"two","title":"Second","type":"cleanup","touches":[],"blocked_by":["one"],'
        '"review_criteria":[],"done":false}',
    )
    plan_path.write_text(head_plan_text, encoding="utf-8")
    module_path.write_text("before\n", encoding="utf-8")
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-m", "seed")
    return plan_path, head_plan_text


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


def test_rewrite_task_done_flips_only_the_selected_task() -> None:
    plan_text = _plan_text(
        '{"id":"one","title":"First","type":"cleanup","touches":["a.py"],'
        '"blocked_by":[],"review_criteria":["preserve \u2192 formatting"],'
        '"done":false}',
        '{"id":"two","title":"Second","type":"cleanup","touches":["b.py"],'
        '"blocked_by":["one"],"review_criteria":[],"done":false}',
    )

    plan = rlrp.parse_plan(plan_text)
    rewritten = rlrp.rewrite_task_done(plan_text, plan.tasks[0])

    assert rewritten.count('"done": true') == 1
    assert rewritten.count('"done":false') == 1
    assert '"touches":["a.py"]' in rewritten
    assert '"review_criteria":["preserve \u2192 formatting"]' in rewritten


def test_pick_next_task_returns_first_unblocked_undone_task() -> None:
    plan = rlrp.parse_plan(
        _plan_text(
            '{"id":"one","title":"First","type":"cleanup","touches":[],"blocked_by":[],'
            '"review_criteria":[],"done":true}',
            '{"id":"two","title":"Second","type":"cleanup","touches":[],"blocked_by":["one"],'
            '"review_criteria":[],"done":false}',
            '{"id":"three","title":"Third","type":"cleanup","touches":[],"blocked_by":["two"],'
            '"review_criteria":[],"done":false}',
        )
    )

    task = rlrp.pick_next_task(plan)

    assert task is not None
    assert task.id == "two"


def test_validate_plan_rejects_unknown_dependency() -> None:
    plan = rlrp.parse_plan(
        _plan_text(
            '{"id":"one","title":"First","type":"cleanup","touches":[],"blocked_by":["missing"],'
            '"review_criteria":[],"done":false}',
        )
    )

    with pytest.raises(SystemExit, match="references unknown dependency missing"):
        rlrp.validate_plan(plan)


def test_rewrite_status_updates_only_the_top_level_status_line() -> None:
    plan_text = _plan_text(
        '{"id":"one","title":"First","type":"cleanup","touches":[],"blocked_by":[],'
        '"review_criteria":["Status: keep this text inside task data"],"done":false}',
        status="todo",
    )

    rewritten = rlrp.rewrite_status(plan_text, "failed -- tests red")

    assert "Status: failed -- tests red" in rewritten
    assert '"review_criteria":["Status: keep this text inside task data"]' in rewritten
    assert rewritten.count("Status:") == 2


def test_recoverable_task_from_plan_texts_rejects_extra_plan_edits() -> None:
    head_plan_text = _plan_text(
        '{"id":"one","title":"First","type":"cleanup","touches":["src/module.py"],'
        '"blocked_by":[],"review_criteria":[],"done":false}',
    )
    task = rlrp.parse_plan(head_plan_text).tasks[0]
    disk_plan_text = rlrp.rewrite_task_done(head_plan_text, task).replace(
        '"title":"First"',
        '"title":"First revised"',
        1,
    )

    assert (
        rlrp._recoverable_task_from_plan_texts(head_plan_text, disk_plan_text) is None
    )


def test_recover_interrupted_success_commits_exact_scope_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_path, head_plan_text = _seed_recovery_repo(tmp_path)
    module_path = tmp_path / "src" / "module.py"
    task = rlrp.parse_plan(head_plan_text).tasks[0]

    plan_path.write_text(
        rlrp.rewrite_task_done(head_plan_text, task),
        encoding="utf-8",
    )
    module_path.write_text("after\n", encoding="utf-8")
    monkeypatch.setattr(rlrp, "PLAN_PATH", plan_path)

    sha = rlrp._recover_interrupted_success(tmp_path)

    assert sha == _git(tmp_path, "rev-parse", "HEAD").strip()
    assert _git(tmp_path, "status", "--short") == ""
    assert set(_git(tmp_path, "show", "--name-only", "--format=", "HEAD").splitlines()) == {
        "docs/plans/larger-refactorings.md",
        "src/module.py",
    }


def test_recover_interrupted_success_refuses_unrelated_dirty_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_path, head_plan_text = _seed_recovery_repo(tmp_path)
    module_path = tmp_path / "src" / "module.py"
    task = rlrp.parse_plan(head_plan_text).tasks[0]
    before_head = _git(tmp_path, "rev-parse", "HEAD").strip()

    plan_path.write_text(
        rlrp.rewrite_task_done(head_plan_text, task),
        encoding="utf-8",
    )
    module_path.write_text("after\n", encoding="utf-8")
    (tmp_path / "user-note.txt").write_text("leave me out of it\n", encoding="utf-8")
    monkeypatch.setattr(rlrp, "PLAN_PATH", plan_path)

    sha = rlrp._recover_interrupted_success(tmp_path)

    assert sha is None
    assert _git(tmp_path, "rev-parse", "HEAD").strip() == before_head
    assert "user-note.txt" in _git(tmp_path, "status", "--short")
