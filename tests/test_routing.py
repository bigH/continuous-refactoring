from __future__ import annotations

import json
from pathlib import Path

import pytest

from continuous_refactoring.artifacts import (
    CommandCapture,
    ContinuousRefactorError,
    RunArtifacts,
    create_run_artifacts,
)
from continuous_refactoring.routing import classify_target
from continuous_refactoring.targeting import Target


_TASTE = "- Prefer deletion over wrapping.\n- Fail fast at boundaries."


def _target() -> Target:
    return Target(
        description="Clean up auth module",
        files=("src/auth.py",),
        scoping="Focus on dead code removal",
    )


def _make_artifacts(tmp_path: Path) -> RunArtifacts:
    return create_run_artifacts(
        repo_root=tmp_path,
        agent="codex",
        model="fake",
        effort="low",
        test_command="true",
    )


def _prepare_tmpdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmpdir"))
    (tmp_path / "tmpdir").mkdir(exist_ok=True)


def _fake_capture(
    stdout: str, *, returncode: int = 0, tmp_path: Path | None = None,
) -> CommandCapture:
    base = tmp_path or Path("/tmp")
    return CommandCapture(
        command=("fake",),
        returncode=returncode,
        stdout=stdout,
        stderr="",
        stdout_path=base / "stdout.log",
        stderr_path=base / "stderr.log",
    )


def _run_with_fake_agent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stdout: str,
    *,
    returncode: int = 0,
    artifacts: RunArtifacts | None = None,
) -> str:
    _prepare_tmpdir(tmp_path, monkeypatch)
    artifacts = artifacts or _make_artifacts(tmp_path)

    def fake_agent(**kwargs: object) -> CommandCapture:
        stdout_path = Path(str(kwargs["stdout_path"]))
        stderr_path = Path(str(kwargs["stderr_path"]))
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.write_text("", encoding="utf-8")
        return _fake_capture(stdout, returncode=returncode, tmp_path=tmp_path)

    monkeypatch.setattr("continuous_refactoring.routing.maybe_run_agent", fake_agent)
    return classify_target(
        _target(),
        _TASTE,
        tmp_path,
        artifacts,
        agent="codex",
        model="fake",
        effort="low",
        timeout=None,
    )


def _call_finished_events(artifacts: RunArtifacts) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for line in artifacts.events_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("event") == "call_finished":
            events.append(event)
    return events


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_classify_cohesive_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        _run_with_fake_agent(
            tmp_path,
            monkeypatch,
            "analysis...\ndecision: cohesive-cleanup \u2014 fits one session\n",
        )
        == "cohesive-cleanup"
    )


def test_classify_needs_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        _run_with_fake_agent(
            tmp_path,
            monkeypatch,
            "thinking...\nDecision: needs-plan \u2014 spans multiple clusters\n",
        )
        == "needs-plan"
    )


def test_classify_case_insensitive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        _run_with_fake_agent(
            tmp_path,
            monkeypatch,
            "DECISION: COHESIVE-CLEANUP \u2014 small scope\n",
        )
        == "cohesive-cleanup"
    )


def test_classify_ignores_trailing_non_matching_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        _run_with_fake_agent(
            tmp_path,
            monkeypatch,
            "\n".join(
                [
                    "analysis",
                    "Decision: needs-plan \u2014 spread across systems",
                    "tooling: wrote artifact summary",
                ],
            ),
        )
        == "needs-plan"
    )


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_classify_malformed_output_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ContinuousRefactorError, match="unrecognised output"):
        _run_with_fake_agent(tmp_path, monkeypatch, "I don't know what to do\n")


def test_classify_malformed_output_logs_failed_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepare_tmpdir(tmp_path, monkeypatch)
    artifacts = _make_artifacts(tmp_path)

    with pytest.raises(ContinuousRefactorError, match="unrecognised output"):
        _run_with_fake_agent(
            tmp_path,
            monkeypatch,
            "I don't know what to do\n",
            artifacts=artifacts,
        )

    event = _call_finished_events(artifacts)[-1]
    timestamp = event.pop("timestamp")

    assert isinstance(timestamp, str)
    assert event == {
        "attempt": 1,
        "call_role": "classify",
        "call_status": "failed",
        "event": "call_finished",
        "level": "WARN",
        "message": "call failed: classify \u2014 Clean up auth module",
        "phase_reached": "classify",
        "retry": 1,
        "returncode": 0,
        "summary": "Classifier produced unrecognised output: \"I don't know what to do\"",
        "target": "Clean up auth module",
    }


def test_classify_empty_output_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ContinuousRefactorError, match="no output"):
        _run_with_fake_agent(tmp_path, monkeypatch, "")


def test_classify_nonzero_exit_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ContinuousRefactorError, match="exit code 1"):
        _run_with_fake_agent(
            tmp_path,
            monkeypatch,
            "decision: cohesive-cleanup\n",
            returncode=1,
        )


def test_classify_nonzero_exit_logs_failed_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepare_tmpdir(tmp_path, monkeypatch)
    artifacts = _make_artifacts(tmp_path)

    with pytest.raises(ContinuousRefactorError, match="exit code 1"):
        _run_with_fake_agent(
            tmp_path,
            monkeypatch,
            "decision: cohesive-cleanup\n",
            returncode=1,
            artifacts=artifacts,
        )

    event = _call_finished_events(artifacts)[-1]
    timestamp = event.pop("timestamp")

    assert isinstance(timestamp, str)
    assert event == {
        "attempt": 1,
        "call_role": "classify",
        "call_status": "failed",
        "event": "call_finished",
        "level": "WARN",
        "message": "call failed: classify \u2014 Clean up auth module",
        "phase_reached": "classify",
        "retry": 1,
        "returncode": 1,
        "summary": "codex exited with code 1",
        "target": "Clean up auth module",
    }


def test_classify_preserves_wrapped_agent_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepare_tmpdir(tmp_path, monkeypatch)
    artifacts = _make_artifacts(tmp_path)
    failure = OSError("launch denied")

    def fail_agent(**_kwargs: object) -> CommandCapture:
        raise ContinuousRefactorError(
            f"Failed to start codex in {tmp_path}: {failure}"
        ) from failure

    monkeypatch.setattr("continuous_refactoring.routing.maybe_run_agent", fail_agent)

    with pytest.raises(ContinuousRefactorError, match="Failed to start codex") as exc_info:
        classify_target(
            _target(),
            _TASTE,
            tmp_path,
            artifacts,
            agent="codex",
            model="fake",
            effort="low",
            timeout=None,
        )

    assert exc_info.value.__cause__ is failure
    event = _call_finished_events(artifacts)[-1]
    assert event["summary"] == f"Failed to start codex in {tmp_path}: {failure}"
