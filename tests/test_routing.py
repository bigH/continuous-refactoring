from __future__ import annotations

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


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_classify_cohesive_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmpdir"))
    (tmp_path / "tmpdir").mkdir()

    def fake_agent(**kwargs: object) -> CommandCapture:
        Path(str(kwargs["stdout_path"])).parent.mkdir(parents=True, exist_ok=True)
        Path(str(kwargs["stdout_path"])).write_text("", encoding="utf-8")
        Path(str(kwargs["stderr_path"])).parent.mkdir(parents=True, exist_ok=True)
        Path(str(kwargs["stderr_path"])).write_text("", encoding="utf-8")
        return _fake_capture(
            "analysis...\ndecision: cohesive-cleanup \u2014 fits one session\n",
            tmp_path=tmp_path,
        )

    monkeypatch.setattr("continuous_refactoring.routing.maybe_run_agent", fake_agent)
    artifacts = _make_artifacts(tmp_path)

    result = classify_target(
        _target(), _TASTE, tmp_path, artifacts,
        agent="codex", model="fake", effort="low", timeout=None,
    )
    assert result == "cohesive-cleanup"


def test_classify_needs_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmpdir"))
    (tmp_path / "tmpdir").mkdir()

    def fake_agent(**kwargs: object) -> CommandCapture:
        Path(str(kwargs["stdout_path"])).parent.mkdir(parents=True, exist_ok=True)
        Path(str(kwargs["stdout_path"])).write_text("", encoding="utf-8")
        Path(str(kwargs["stderr_path"])).parent.mkdir(parents=True, exist_ok=True)
        Path(str(kwargs["stderr_path"])).write_text("", encoding="utf-8")
        return _fake_capture(
            "thinking...\nDecision: needs-plan \u2014 spans multiple clusters\n",
            tmp_path=tmp_path,
        )

    monkeypatch.setattr("continuous_refactoring.routing.maybe_run_agent", fake_agent)
    artifacts = _make_artifacts(tmp_path)

    result = classify_target(
        _target(), _TASTE, tmp_path, artifacts,
        agent="codex", model="fake", effort="low", timeout=None,
    )
    assert result == "needs-plan"


def test_classify_case_insensitive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmpdir"))
    (tmp_path / "tmpdir").mkdir()

    def fake_agent(**kwargs: object) -> CommandCapture:
        Path(str(kwargs["stdout_path"])).parent.mkdir(parents=True, exist_ok=True)
        Path(str(kwargs["stdout_path"])).write_text("", encoding="utf-8")
        Path(str(kwargs["stderr_path"])).parent.mkdir(parents=True, exist_ok=True)
        Path(str(kwargs["stderr_path"])).write_text("", encoding="utf-8")
        return _fake_capture(
            "DECISION: COHESIVE-CLEANUP \u2014 small scope\n",
            tmp_path=tmp_path,
        )

    monkeypatch.setattr("continuous_refactoring.routing.maybe_run_agent", fake_agent)
    artifacts = _make_artifacts(tmp_path)

    result = classify_target(
        _target(), _TASTE, tmp_path, artifacts,
        agent="codex", model="fake", effort="low", timeout=None,
    )
    assert result == "cohesive-cleanup"


def test_classify_ignores_trailing_non_matching_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmpdir"))
    (tmp_path / "tmpdir").mkdir()

    def fake_agent(**kwargs: object) -> CommandCapture:
        Path(str(kwargs["stdout_path"])).parent.mkdir(parents=True, exist_ok=True)
        Path(str(kwargs["stdout_path"])).write_text("", encoding="utf-8")
        Path(str(kwargs["stderr_path"])).parent.mkdir(parents=True, exist_ok=True)
        Path(str(kwargs["stderr_path"])).write_text("", encoding="utf-8")
        return _fake_capture(
            "\n".join(
                [
                    "analysis",
                    "Decision: needs-plan \u2014 spread across systems",
                    "tooling: wrote artifact summary",
                ],
            ),
            tmp_path=tmp_path,
        )

    monkeypatch.setattr("continuous_refactoring.routing.maybe_run_agent", fake_agent)
    artifacts = _make_artifacts(tmp_path)

    result = classify_target(
        _target(), _TASTE, tmp_path, artifacts,
        agent="codex", model="fake", effort="low", timeout=None,
    )
    assert result == "needs-plan"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_classify_malformed_output_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmpdir"))
    (tmp_path / "tmpdir").mkdir()

    def fake_agent(**kwargs: object) -> CommandCapture:
        Path(str(kwargs["stdout_path"])).parent.mkdir(parents=True, exist_ok=True)
        Path(str(kwargs["stdout_path"])).write_text("", encoding="utf-8")
        Path(str(kwargs["stderr_path"])).parent.mkdir(parents=True, exist_ok=True)
        Path(str(kwargs["stderr_path"])).write_text("", encoding="utf-8")
        return _fake_capture("I don't know what to do\n", tmp_path=tmp_path)

    monkeypatch.setattr("continuous_refactoring.routing.maybe_run_agent", fake_agent)
    artifacts = _make_artifacts(tmp_path)

    with pytest.raises(ContinuousRefactorError, match="unrecognised output"):
        classify_target(
            _target(), _TASTE, tmp_path, artifacts,
            agent="codex", model="fake", effort="low", timeout=None,
        )


def test_classify_empty_output_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmpdir"))
    (tmp_path / "tmpdir").mkdir()

    def fake_agent(**kwargs: object) -> CommandCapture:
        Path(str(kwargs["stdout_path"])).parent.mkdir(parents=True, exist_ok=True)
        Path(str(kwargs["stdout_path"])).write_text("", encoding="utf-8")
        Path(str(kwargs["stderr_path"])).parent.mkdir(parents=True, exist_ok=True)
        Path(str(kwargs["stderr_path"])).write_text("", encoding="utf-8")
        return _fake_capture("", tmp_path=tmp_path)

    monkeypatch.setattr("continuous_refactoring.routing.maybe_run_agent", fake_agent)
    artifacts = _make_artifacts(tmp_path)

    with pytest.raises(ContinuousRefactorError, match="no output"):
        classify_target(
            _target(), _TASTE, tmp_path, artifacts,
            agent="codex", model="fake", effort="low", timeout=None,
        )


def test_classify_nonzero_exit_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmpdir"))
    (tmp_path / "tmpdir").mkdir()

    def fake_agent(**kwargs: object) -> CommandCapture:
        Path(str(kwargs["stdout_path"])).parent.mkdir(parents=True, exist_ok=True)
        Path(str(kwargs["stdout_path"])).write_text("", encoding="utf-8")
        Path(str(kwargs["stderr_path"])).parent.mkdir(parents=True, exist_ok=True)
        Path(str(kwargs["stderr_path"])).write_text("", encoding="utf-8")
        return _fake_capture(
            "decision: cohesive-cleanup\n",
            returncode=1,
            tmp_path=tmp_path,
        )

    monkeypatch.setattr("continuous_refactoring.routing.maybe_run_agent", fake_agent)
    artifacts = _make_artifacts(tmp_path)

    with pytest.raises(ContinuousRefactorError, match="exit code 1"):
        classify_target(
            _target(), _TASTE, tmp_path, artifacts,
            agent="codex", model="fake", effort="low", timeout=None,
        )
