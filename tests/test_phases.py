from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from continuous_refactoring.artifacts import (
    CommandCapture,
    RunArtifacts,
    create_run_artifacts,
    ContinuousRefactorError,
)
from continuous_refactoring.migrations import (
    MigrationManifest,
    PhaseSpec,
    bump_last_touch,
    load_manifest,
    migration_root,
    save_manifest,
)
from continuous_refactoring.phases import (
    ExecutePhaseOutcome,
    check_phase_ready,
    execute_phase,
)


_TASTE = "- Prefer deletion over wrapping.\n- Fail fast at boundaries."
_MIGRATION = "rework-auth"

_PHASE_0 = PhaseSpec(
    name="setup", file="phase-0-setup.md", done=False, precondition="always",
)
_PHASE_1 = PhaseSpec(
    name="migrate", file="phase-1-migrate.md", done=False,
    precondition="phase 0 complete",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _make_manifest(*, last_touch: str | None = None) -> MigrationManifest:
    now = last_touch or _now_iso()
    return MigrationManifest(
        name=_MIGRATION,
        created_at=now,
        last_touch=now,
        wake_up_on=None,
        awaiting_human_review=False,
        status="in-progress",
        current_phase="setup",
        phases=(_PHASE_0, _PHASE_1),
    )


def _make_artifacts(tmp_path: Path) -> RunArtifacts:
    return create_run_artifacts(
        repo_root=tmp_path,
        agent="codex",
        model="fake",
        effort="low",
        test_command="true",
    )


def _events(artifacts: RunArtifacts) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in artifacts.events_path.read_text(encoding="utf-8").splitlines()
    ]


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


def _save_manifest_to_disk(manifest: MigrationManifest, live_dir: Path) -> Path:
    mig_root = migration_root(live_dir, manifest.name)
    mig_root.mkdir(parents=True, exist_ok=True)
    manifest_path = mig_root / "manifest.json"
    save_manifest(manifest, manifest_path)
    return manifest_path


def _patch_agent(
    monkeypatch: pytest.MonkeyPatch, stdout: str, tmp_path: Path,
) -> None:
    def fake_agent(**kwargs: object) -> CommandCapture:
        for key in ("stdout_path", "stderr_path"):
            path = Path(str(kwargs[key]))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        return _fake_capture(stdout, tmp_path=tmp_path)

    monkeypatch.setattr(
        "continuous_refactoring.phases.maybe_run_agent", fake_agent,
    )


def _status_block(
    *,
    phase_reached: str = "refactor",
    decision: str = "commit",
    failure_kind: str = "none",
    summary: str = "Ready to commit.",
    next_retry_focus: str = "none",
) -> str:
    return f"""\
BEGIN_CONTINUOUS_REFACTORING_STATUS
phase_reached: {phase_reached}
decision: {decision}
retry_recommendation: none
failure_kind: {failure_kind}
summary: {summary}
next_retry_focus: {next_retry_focus}
tests_run: none
evidence:
  - none
END_CONTINUOUS_REFACTORING_STATUS
"""


def _patch_status_agent(
    monkeypatch: pytest.MonkeyPatch,
    stdout: str,
    tmp_path: Path,
    *,
    returncode: int = 0,
    prompts: list[str] | None = None,
) -> None:
    def fake_agent(**kwargs: object) -> CommandCapture:
        if prompts is not None:
            prompts.append(str(kwargs.get("prompt", "")))
        for key in ("stdout_path", "stderr_path"):
            path = Path(str(kwargs[key]))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        return _fake_capture(stdout, returncode=returncode, tmp_path=tmp_path)

    monkeypatch.setattr(
        "continuous_refactoring.phases.maybe_run_agent", fake_agent,
    )


@pytest.fixture(autouse=True)
def _isolate_tmpdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "tmpdir").mkdir()
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmpdir"))


def _passing_tests(
    test_command: str,
    repo_root: Path,
    stdout_path: Path,
    stderr_path: Path,
    **kwargs: object,
) -> CommandCapture:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text("ok\n", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    return CommandCapture(
        command=("pytest",), returncode=0, stdout="ok\n", stderr="",
        stdout_path=stdout_path, stderr_path=stderr_path,
    )


def _failing_tests(
    test_command: str,
    repo_root: Path,
    stdout_path: Path,
    stderr_path: Path,
    **kwargs: object,
) -> CommandCapture:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text("FAILED\n", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    return CommandCapture(
        command=("pytest",), returncode=1, stdout="FAILED\n", stderr="",
        stdout_path=stdout_path, stderr_path=stderr_path,
    )


# ---------------------------------------------------------------------------
# check_phase_ready
# ---------------------------------------------------------------------------


def test_check_ready_yes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_agent(monkeypatch, "checking...\nready: yes\n", tmp_path)

    verdict, reason = check_phase_ready(
        _PHASE_0, _make_manifest(), tmp_path, _make_artifacts(tmp_path),
        taste=_TASTE, agent="codex", model="fake", effort="low", timeout=None,
    )
    assert verdict == "yes"
    assert reason == "yes"


def test_check_ready_yes_with_trailing_noise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_agent(
        monkeypatch,
        "ready: yes\nthis line should not veto readiness\n",
        tmp_path,
    )

    verdict, reason = check_phase_ready(
        _PHASE_0, _make_manifest(), tmp_path, _make_artifacts(tmp_path),
        taste=_TASTE, agent="codex", model="fake", effort="low", timeout=None,
    )
    assert verdict == "yes"
    assert reason == "yes"


def test_check_ready_rejects_no_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_agent(monkeypatch, "", tmp_path)

    with pytest.raises(ContinuousRefactorError, match="no output"):
        check_phase_ready(
            _PHASE_0, _make_manifest(), tmp_path, _make_artifacts(tmp_path),
            taste=_TASTE, agent="codex", model="fake", effort="low", timeout=None,
        )


def test_check_ready_rejects_unparseable_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_agent(
        monkeypatch, "analysis summary\nstatus: inconclusive\n", tmp_path,
    )

    with pytest.raises(ContinuousRefactorError, match="unrecognised output"):
        check_phase_ready(
            _PHASE_0, _make_manifest(), tmp_path, _make_artifacts(tmp_path),
            taste=_TASTE, agent="codex", model="fake", effort="low", timeout=None,
        )


def test_check_ready_propagates_agent_cause(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    failure = OSError("agent transport is down")

    def fail_agent(*_args: object, **_kwargs: object) -> None:
        raise ContinuousRefactorError("agent command failed") from failure

    monkeypatch.setattr(
        "continuous_refactoring.phases.maybe_run_agent",
        fail_agent,
    )

    with pytest.raises(ContinuousRefactorError, match="agent command failed") as exc_info:
        check_phase_ready(
            _PHASE_0, _make_manifest(), tmp_path, _make_artifacts(tmp_path),
            taste=_TASTE, agent="codex", model="fake", effort="low", timeout=None,
        )

    assert exc_info.value.__cause__ is failure


def test_check_ready_nonzero_exit_wraps_called_process_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_status_agent(monkeypatch, "ready: yes\n", tmp_path, returncode=7)

    with pytest.raises(
        ContinuousRefactorError,
        match="Phase ready-check agent failed with exit code 7",
    ) as exc_info:
        check_phase_ready(
            _PHASE_0, _make_manifest(), tmp_path, _make_artifacts(tmp_path),
            taste=_TASTE, agent="codex", model="fake", effort="low", timeout=None,
        )

    cause = exc_info.value.__cause__
    assert isinstance(cause, subprocess.CalledProcessError)
    assert cause.returncode == 7


def test_check_ready_no(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_agent(
        monkeypatch,
        "checking...\nready: no — prerequisites not met\n",
        tmp_path,
    )

    verdict, reason = check_phase_ready(
        _PHASE_0, _make_manifest(), tmp_path, _make_artifacts(tmp_path),
        taste=_TASTE, agent="codex", model="fake", effort="low", timeout=None,
    )
    assert verdict == "no"
    assert reason == "prerequisites not met"


def test_check_ready_unverifiable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_agent(
        monkeypatch,
        "analysis...\nready: unverifiable — need human judgment\n",
        tmp_path,
    )

    verdict, reason = check_phase_ready(
        _PHASE_0, _make_manifest(), tmp_path, _make_artifacts(tmp_path),
        taste=_TASTE, agent="codex", model="fake", effort="low", timeout=None,
    )
    assert verdict == "unverifiable"
    assert reason == "need human judgment"


def test_check_ready_prompt_includes_taste(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts: list[str] = []

    def fake_agent(**kwargs: object) -> CommandCapture:
        prompts.append(str(kwargs["prompt"]))
        for key in ("stdout_path", "stderr_path"):
            path = Path(str(kwargs[key]))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        return _fake_capture("ready: yes\n", tmp_path=tmp_path)

    monkeypatch.setattr(
        "continuous_refactoring.phases.maybe_run_agent", fake_agent,
    )

    check_phase_ready(
        _PHASE_0, _make_manifest(), tmp_path, _make_artifacts(tmp_path),
        taste=_TASTE, agent="codex", model="fake", effort="low", timeout=None,
    )

    assert len(prompts) == 1
    assert f"## Taste\n{_TASTE}" in prompts[0]


def test_phase_ready_check_call_message_uses_phase_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_agent(monkeypatch, "ready: yes\n", tmp_path)
    artifacts = _make_artifacts(tmp_path)

    check_phase_ready(
        _PHASE_0,
        _make_manifest(),
        tmp_path,
        artifacts,
        taste=_TASTE,
        agent="codex",
        model="fake",
        effort="low",
        timeout=None,
    )

    call_events = [
        event for event in _events(artifacts)
        if event.get("call_role") == "phase.ready-check"
    ]
    assert [event["message"] for event in call_events] == [
        "call start: phase.ready-check — setup",
        "call finished: phase.ready-check — setup",
    ]
    assert {event["target"] for event in call_events} == {
        "rework-auth phase-0-setup.md (setup)",
    }
    log_text = artifacts.log_path.read_text(encoding="utf-8")
    assert "phase.ready-check — setup" in log_text
    assert "rework-auth phase-0-setup.md" not in log_text


# ---------------------------------------------------------------------------
# ready=yes path with green tests flips phase.done
# ---------------------------------------------------------------------------


def test_ready_yes_green_tests_flips_phase_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = tmp_path / "live"
    manifest = _make_manifest()
    manifest_path = _save_manifest_to_disk(manifest, live_dir)

    monkeypatch.setattr(
        "continuous_refactoring.phases.get_head_sha", lambda _: "abc123",
    )
    _patch_agent(monkeypatch, "executed phase work\n", tmp_path)
    monkeypatch.setattr("continuous_refactoring.phases.run_tests", _passing_tests)

    outcome = execute_phase(
        _PHASE_0,
        manifest,
        _TASTE,
        tmp_path,
        live_dir,
        _make_artifacts(tmp_path),
        agent="codex",
        model="fake",
        effort="low",
        timeout=None,
        validation_command="true",
        max_attempts=1,
    )

    assert outcome.status == "done"

    reloaded = load_manifest(manifest_path)
    assert reloaded.phases[0].done is True
    assert reloaded.phases[1].done is False
    assert reloaded.current_phase == "migrate"


def test_execute_phase_call_messages_use_phase_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = tmp_path / "live"
    manifest = _make_manifest()
    _save_manifest_to_disk(manifest, live_dir)
    artifacts = _make_artifacts(tmp_path)

    monkeypatch.setattr(
        "continuous_refactoring.phases.get_head_sha", lambda _: "abc123",
    )
    _patch_agent(monkeypatch, "executed phase work\n", tmp_path)
    monkeypatch.setattr("continuous_refactoring.phases.run_tests", _passing_tests)

    outcome = execute_phase(
        _PHASE_0,
        manifest,
        _TASTE,
        tmp_path,
        live_dir,
        artifacts,
        agent="codex",
        model="fake",
        effort="low",
        timeout=None,
        validation_command="true",
        max_attempts=1,
    )

    assert outcome.status == "done"
    call_messages = [
        str(event["message"]) for event in _events(artifacts)
        if event.get("call_role") in {"phase.execute", "phase.validation"}
    ]
    assert call_messages == [
        "call start: phase.execute — setup",
        "call finished: phase.execute — setup",
        "call start: phase.validation — setup",
        "call finished: phase.validation — setup",
    ]
    assert "rework-auth phase-0-setup.md" not in artifacts.log_path.read_text(
        encoding="utf-8",
    )


def test_final_phase_completion_marks_migration_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = tmp_path / "live"
    manifest = replace(
        _make_manifest(),
        current_phase="migrate",
        phases=(replace(_PHASE_0, done=True), _PHASE_1),
    )
    manifest_path = _save_manifest_to_disk(manifest, live_dir)

    monkeypatch.setattr(
        "continuous_refactoring.phases.get_head_sha", lambda _: "abc123",
    )
    _patch_agent(monkeypatch, "executed final phase\n", tmp_path)
    monkeypatch.setattr("continuous_refactoring.phases.run_tests", _passing_tests)

    outcome = execute_phase(
        _PHASE_1,
        manifest,
        _TASTE,
        tmp_path,
        live_dir,
        _make_artifacts(tmp_path),
        agent="codex",
        model="fake",
        effort="low",
        timeout=None,
        validation_command="true",
        max_attempts=1,
    )

    assert outcome.status == "done"

    reloaded = load_manifest(manifest_path)
    assert reloaded.status == "done"
    assert reloaded.current_phase == ""
    assert reloaded.phases[0].done is True
    assert reloaded.phases[1].done is True


def test_execute_phase_success_clears_deferred_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = tmp_path / "live"
    old_touch = "2020-01-01T00:00:00.000+00:00"
    manifest = replace(
        _make_manifest(last_touch=old_touch),
        wake_up_on="2020-01-08T00:00:00.000+00:00",
        awaiting_human_review=True,
        human_review_reason="needs a person",
        cooldown_until="2020-01-01T06:00:00.000+00:00",
    )
    manifest_path = _save_manifest_to_disk(manifest, live_dir)

    monkeypatch.setattr(
        "continuous_refactoring.phases.get_head_sha", lambda _: "abc123",
    )
    _patch_agent(monkeypatch, "executed phase work\n", tmp_path)
    monkeypatch.setattr("continuous_refactoring.phases.run_tests", _passing_tests)

    outcome = execute_phase(
        _PHASE_0,
        manifest,
        _TASTE,
        tmp_path,
        live_dir,
        _make_artifacts(tmp_path),
        agent="codex",
        model="fake",
        effort="low",
        timeout=None,
        validation_command="true",
        max_attempts=1,
    )

    assert outcome.status == "done"

    reloaded = load_manifest(manifest_path)
    assert reloaded.last_touch != old_touch
    assert reloaded.wake_up_on is None
    assert reloaded.awaiting_human_review is False
    assert reloaded.human_review_reason is None
    assert reloaded.cooldown_until is None
    assert reloaded.current_phase == "migrate"


# ---------------------------------------------------------------------------
# ready=no leaves manifest untouched except last_touch + wake_up_on bump
# ---------------------------------------------------------------------------


def test_ready_no_leaves_manifest_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = tmp_path / "live"
    old_touch = "2020-01-01T00:00:00.000+00:00"
    manifest = _make_manifest(last_touch=old_touch)
    manifest_path = _save_manifest_to_disk(manifest, live_dir)
    original = load_manifest(manifest_path)

    _patch_agent(monkeypatch, "ready: no — not ready yet\n", tmp_path)

    verdict, _reason = check_phase_ready(
        _PHASE_0, manifest, tmp_path, _make_artifacts(tmp_path),
        taste=_TASTE, agent="codex", model="fake", effort="low", timeout=None,
    )
    assert verdict == "no"

    # Simulate caller behavior (T4.3): bump last_touch + set wake_up_on
    now = datetime.now(timezone.utc)
    updated = bump_last_touch(manifest, now)
    wake_target = (now + timedelta(days=7)).isoformat(timespec="milliseconds")
    updated = replace(updated, wake_up_on=wake_target)
    save_manifest(updated, manifest_path)

    reloaded = load_manifest(manifest_path)
    assert reloaded.phases == original.phases
    assert reloaded.current_phase == original.current_phase
    assert reloaded.status == original.status
    assert reloaded.awaiting_human_review == original.awaiting_human_review
    assert reloaded.last_touch != original.last_touch
    assert reloaded.wake_up_on is not None


# ---------------------------------------------------------------------------
# ready=unverifiable sets manifest.awaiting_human_review=True
# ---------------------------------------------------------------------------


def test_ready_unverifiable_sets_awaiting_human_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = tmp_path / "live"
    manifest = _make_manifest()
    manifest_path = _save_manifest_to_disk(manifest, live_dir)
    assert load_manifest(manifest_path).awaiting_human_review is False

    _patch_agent(
        monkeypatch, "ready: unverifiable — external dependency\n", tmp_path,
    )

    verdict, _reason = check_phase_ready(
        _PHASE_0, manifest, tmp_path, _make_artifacts(tmp_path),
        taste=_TASTE, agent="codex", model="fake", effort="low", timeout=None,
    )
    assert verdict == "unverifiable"

    # Simulate caller behavior (T4.3): flag for human review
    updated = replace(manifest, awaiting_human_review=True)
    save_manifest(updated, manifest_path)

    reloaded = load_manifest(manifest_path)
    assert reloaded.awaiting_human_review is True


# ---------------------------------------------------------------------------
# execute_phase validation + retry behavior
# ---------------------------------------------------------------------------


def test_execute_phase_test_failure_reverts_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = tmp_path / "live"
    manifest = _make_manifest()
    manifest_path = _save_manifest_to_disk(manifest, live_dir)
    original = load_manifest(manifest_path)

    reverted: list[str] = []
    monkeypatch.setattr(
        "continuous_refactoring.phases.get_head_sha", lambda _: "abc123",
    )
    monkeypatch.setattr(
        "continuous_refactoring.phases.revert_to",
        lambda _repo, head: reverted.append(head),
    )
    _patch_agent(monkeypatch, "made changes\n", tmp_path)
    monkeypatch.setattr("continuous_refactoring.phases.run_tests", _failing_tests)

    outcome = execute_phase(
        _PHASE_0,
        manifest,
        _TASTE,
        tmp_path,
        live_dir,
        _make_artifacts(tmp_path),
        agent="codex",
        model="fake",
        effort="low",
        timeout=None,
        validation_command="true",
        max_attempts=1,
    )

    assert outcome.status == "failed"
    assert "validation failed after phase execution" in outcome.reason
    assert reverted == ["abc123"]

    reloaded = load_manifest(manifest_path)
    assert reloaded.phases == original.phases
    assert reloaded.current_phase == original.current_phase


def test_execute_phase_requires_configured_validation_green_even_when_agent_claims_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = tmp_path / "live"
    manifest = _make_manifest()
    manifest_path = _save_manifest_to_disk(manifest, live_dir)
    original = load_manifest(manifest_path)
    validation_calls: list[str] = []

    monkeypatch.setattr(
        "continuous_refactoring.phases.get_head_sha", lambda _: "abc123",
    )
    monkeypatch.setattr(
        "continuous_refactoring.phases.revert_to",
        lambda _repo, _head: None,
    )
    _patch_status_agent(
        monkeypatch,
        _status_block(summary="agent claims phase is done"),
        tmp_path,
    )

    def fail_configured_validation(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        validation_calls.append(test_command)
        return _failing_tests(test_command, repo_root, stdout_path, stderr_path)

    monkeypatch.setattr(
        "continuous_refactoring.phases.run_tests",
        fail_configured_validation,
    )

    outcome = execute_phase(
        _PHASE_0,
        manifest,
        _TASTE,
        tmp_path,
        live_dir,
        _make_artifacts(tmp_path),
        agent="codex",
        model="fake",
        effort="low",
        timeout=None,
        validation_command="custom validation",
        max_attempts=1,
    )

    assert outcome.status == "failed"
    assert outcome.call_role == "phase.validation"
    assert outcome.failure_kind == "validation-failed"
    assert validation_calls == ["custom validation"]
    reloaded = load_manifest(manifest_path)
    assert reloaded.phases == original.phases
    assert reloaded.current_phase == original.current_phase


def test_execute_phase_agent_exception_fails_and_preserves_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = tmp_path / "live"
    manifest = _make_manifest()
    manifest_path = _save_manifest_to_disk(manifest, live_dir)
    original = manifest_path.read_text(encoding="utf-8")
    artifacts = _make_artifacts(tmp_path)

    reverted: list[str] = []
    monkeypatch.setattr(
        "continuous_refactoring.phases.get_head_sha", lambda _: "abc123",
    )
    monkeypatch.setattr(
        "continuous_refactoring.phases.revert_to",
        lambda _repo, head: reverted.append(head),
    )

    def broken_agent(**kwargs: object) -> CommandCapture:
        raise ContinuousRefactorError(
            f"codex exec --model fake HUGE-PROMPT\nfailed inside {tmp_path}"
        )

    def fail_if_called(*args: object, **kwargs: object) -> CommandCapture:
        pytest.fail("validation should not run after agent execution failure")

    monkeypatch.setattr(
        "continuous_refactoring.phases.maybe_run_agent", broken_agent,
    )
    monkeypatch.setattr("continuous_refactoring.phases.run_tests", fail_if_called)

    outcome = execute_phase(
        _PHASE_0,
        manifest,
        _TASTE,
        tmp_path,
        live_dir,
        artifacts,
        agent="codex",
        model="fake",
        effort="low",
        timeout=None,
        validation_command="true",
        max_attempts=1,
    )

    assert outcome == ExecutePhaseOutcome(
        status="failed",
        reason="failed inside <repo>",
        call_role="phase.execute",
        phase_reached="phase.execute",
        failure_kind="agent-infra-failure",
        retry=1,
    )
    assert reverted == ["abc123"]
    assert artifacts.attempts[1].failure_summary == "failed inside <repo>"
    assert manifest_path.read_text(encoding="utf-8") == original


def test_execute_phase_agent_nonzero_uses_status_fallback_without_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = tmp_path / "live"
    manifest = _make_manifest()
    manifest_path = _save_manifest_to_disk(manifest, live_dir)
    original = manifest_path.read_text(encoding="utf-8")

    reverted: list[str] = []
    validation_called = False
    monkeypatch.setattr(
        "continuous_refactoring.phases.get_head_sha", lambda _: "abc123",
    )
    monkeypatch.setattr(
        "continuous_refactoring.phases.revert_to",
        lambda _repo, head: reverted.append(head),
    )
    _patch_status_agent(
        monkeypatch,
        _status_block(phase_reached="refactor", summary="agent status summary"),
        tmp_path,
        returncode=17,
    )

    def fail_if_called(*args: object, **kwargs: object) -> CommandCapture:
        nonlocal validation_called
        validation_called = True
        pytest.fail("validation should not run after nonzero agent exit")

    monkeypatch.setattr("continuous_refactoring.phases.run_tests", fail_if_called)

    outcome = execute_phase(
        _PHASE_0,
        manifest,
        _TASTE,
        tmp_path,
        live_dir,
        _make_artifacts(tmp_path),
        agent="codex",
        model="fake",
        effort="low",
        timeout=None,
        validation_command="true",
        max_attempts=1,
    )

    assert outcome.status == "failed"
    assert outcome.call_role == "phase.execute"
    assert outcome.phase_reached == "refactor"
    assert outcome.failure_kind == "agent-exited-nonzero"
    assert outcome.reason == "agent status summary"
    assert reverted == ["abc123"]
    assert validation_called is False
    assert manifest_path.read_text(encoding="utf-8") == original


def test_execute_phase_retries_after_validation_failure_and_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = tmp_path / "live"
    manifest = _make_manifest()
    manifest_path = _save_manifest_to_disk(manifest, live_dir)

    prompts: list[str] = []
    validation_calls = 0
    reverted: list[str] = []

    monkeypatch.setattr(
        "continuous_refactoring.phases.get_head_sha", lambda _: "abc123",
    )
    monkeypatch.setattr(
        "continuous_refactoring.phases.revert_to",
        lambda _repo, head: reverted.append(head),
    )

    def fake_agent(**kwargs: object) -> CommandCapture:
        prompts.append(str(kwargs.get("prompt", "")))
        stdout_path = Path(str(kwargs["stdout_path"]))
        stderr_path = Path(str(kwargs["stderr_path"]))
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text("done\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return CommandCapture(
            command=("fake",),
            returncode=0,
            stdout="done\n",
            stderr="",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )

    def fail_once_then_pass(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        nonlocal validation_calls
        validation_calls += 1
        assert test_command == "uv run pytest -q"
        if validation_calls == 1:
            return _failing_tests(test_command, repo_root, stdout_path, stderr_path)
        return _passing_tests(test_command, repo_root, stdout_path, stderr_path)

    monkeypatch.setattr("continuous_refactoring.phases.maybe_run_agent", fake_agent)
    monkeypatch.setattr("continuous_refactoring.phases.run_tests", fail_once_then_pass)

    outcome = execute_phase(
        _PHASE_0,
        manifest,
        _TASTE,
        tmp_path,
        live_dir,
        _make_artifacts(tmp_path),
        agent="codex",
        model="fake",
        effort="low",
        timeout=None,
        validation_command="uv run pytest -q",
        max_attempts=2,
    )

    assert outcome.status == "done"
    assert outcome.retry == 2
    assert validation_calls == 2
    assert reverted == ["abc123", "abc123"]
    assert len(prompts) == 2
    assert "## Retry Context" not in prompts[0]
    assert "## Retry Context" in prompts[1]
    assert "failed during `phase.validation`" in prompts[1]
    assert "validation failed after phase execution" in prompts[1]

    reloaded = load_manifest(manifest_path)
    assert reloaded.phases[0].done is True


def test_execute_phase_validation_infra_failure_retries_then_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = tmp_path / "live"
    manifest = _make_manifest()
    manifest_path = _save_manifest_to_disk(manifest, live_dir)
    original = manifest_path.read_text(encoding="utf-8")

    prompts: list[str] = []
    validation_calls = 0
    reverted: list[str] = []

    monkeypatch.setattr(
        "continuous_refactoring.phases.get_head_sha", lambda _: "abc123",
    )
    monkeypatch.setattr(
        "continuous_refactoring.phases.revert_to",
        lambda _repo, head: reverted.append(head),
    )
    _patch_status_agent(
        monkeypatch,
        _status_block(
            phase_reached="refactor",
            summary="agent says retryable",
            next_retry_focus="use the agent focus",
        ),
        tmp_path,
        prompts=prompts,
    )

    def broken_validation(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        nonlocal validation_calls
        validation_calls += 1
        raise ContinuousRefactorError(
            f"RAW-VALIDATION-OUTPUT leaked from {tmp_path}"
        )

    monkeypatch.setattr(
        "continuous_refactoring.phases.run_tests", broken_validation,
    )

    outcome = execute_phase(
        _PHASE_0,
        manifest,
        _TASTE,
        tmp_path,
        live_dir,
        _make_artifacts(tmp_path),
        agent="codex",
        model="fake",
        effort="low",
        timeout=None,
        validation_command="true",
        max_attempts=2,
    )

    assert outcome.status == "failed"
    assert outcome.call_role == "phase.validation"
    assert outcome.phase_reached == "refactor"
    assert outcome.failure_kind == "validation-infra-failure"
    assert outcome.reason == "agent says retryable"
    assert outcome.retry == 2
    assert validation_calls == 2
    assert len(prompts) == 2
    assert "## Retry Context" in prompts[1]
    assert "agent says retryable" in prompts[1]
    assert "use the agent focus" in prompts[1]
    assert "RAW-VALIDATION-OUTPUT" not in prompts[1]
    assert reverted == ["abc123", "abc123", "abc123"]
    assert manifest_path.read_text(encoding="utf-8") == original


def test_execute_phase_unlimited_retries_until_validation_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = tmp_path / "live"
    manifest = _make_manifest()
    manifest_path = _save_manifest_to_disk(manifest, live_dir)

    validation_calls = 0
    reverted: list[str] = []

    monkeypatch.setattr(
        "continuous_refactoring.phases.get_head_sha", lambda _: "abc123",
    )
    monkeypatch.setattr(
        "continuous_refactoring.phases.revert_to",
        lambda _repo, head: reverted.append(head),
    )
    _patch_status_agent(
        monkeypatch,
        _status_block(summary="agent says keep trying"),
        tmp_path,
    )

    def fail_three_times_then_pass(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        nonlocal validation_calls
        validation_calls += 1
        if validation_calls <= 3:
            return _failing_tests(test_command, repo_root, stdout_path, stderr_path)
        return _passing_tests(test_command, repo_root, stdout_path, stderr_path)

    monkeypatch.setattr(
        "continuous_refactoring.phases.run_tests", fail_three_times_then_pass,
    )

    outcome = execute_phase(
        _PHASE_0,
        manifest,
        _TASTE,
        tmp_path,
        live_dir,
        _make_artifacts(tmp_path),
        agent="codex",
        model="fake",
        effort="low",
        timeout=None,
        validation_command="true",
        max_attempts=None,
    )

    assert outcome.status == "done"
    assert outcome.retry == 4
    assert validation_calls == 4
    assert reverted == [
        "abc123",
        "abc123",
        "abc123",
        "abc123",
        "abc123",
        "abc123",
    ]

    reloaded = load_manifest(manifest_path)
    assert reloaded.phases[0].done is True


def test_execute_phase_exhausts_retry_budget_on_validation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = tmp_path / "live"
    manifest = _make_manifest()
    manifest_path = _save_manifest_to_disk(manifest, live_dir)
    original = load_manifest(manifest_path)

    prompts: list[str] = []
    reverted: list[str] = []

    monkeypatch.setattr(
        "continuous_refactoring.phases.get_head_sha", lambda _: "abc123",
    )
    monkeypatch.setattr(
        "continuous_refactoring.phases.revert_to",
        lambda _repo, head: reverted.append(head),
    )

    def fake_agent(**kwargs: object) -> CommandCapture:
        prompts.append(str(kwargs.get("prompt", "")))
        stdout_path = Path(str(kwargs["stdout_path"]))
        stderr_path = Path(str(kwargs["stderr_path"]))
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text("done\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return CommandCapture(
            command=("fake",),
            returncode=0,
            stdout="done\n",
            stderr="",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )

    monkeypatch.setattr("continuous_refactoring.phases.maybe_run_agent", fake_agent)
    monkeypatch.setattr("continuous_refactoring.phases.run_tests", _failing_tests)

    outcome = execute_phase(
        _PHASE_0,
        manifest,
        _TASTE,
        tmp_path,
        live_dir,
        _make_artifacts(tmp_path),
        agent="codex",
        model="fake",
        effort="low",
        timeout=None,
        validation_command="true",
        max_attempts=3,
    )

    assert outcome.status == "failed"
    assert outcome.call_role == "phase.validation"
    assert outcome.failure_kind == "validation-failed"
    assert outcome.retry == 3
    assert len(prompts) == 3
    assert reverted == ["abc123", "abc123", "abc123", "abc123", "abc123"]

    reloaded = load_manifest(manifest_path)
    assert reloaded.phases == original.phases
    assert reloaded.current_phase == original.current_phase


def test_execute_phase_unknown_phase_does_not_mark_manifest_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = tmp_path / "live"
    manifest = _make_manifest()
    manifest_path = _save_manifest_to_disk(manifest, live_dir)
    original = manifest_path.read_text(encoding="utf-8")
    unknown_phase = PhaseSpec(
        name="missing", file="phase-9-missing.md", done=False,
        precondition="not in manifest",
    )

    def fail_if_called(*args: object, **kwargs: object) -> object:
        pytest.fail("unknown phases must fail before side effects")

    monkeypatch.setattr("continuous_refactoring.phases.get_head_sha", fail_if_called)
    monkeypatch.setattr("continuous_refactoring.phases.maybe_run_agent", fail_if_called)
    monkeypatch.setattr("continuous_refactoring.phases.run_tests", fail_if_called)
    monkeypatch.setattr("continuous_refactoring.phases.revert_to", fail_if_called)

    with pytest.raises(ContinuousRefactorError, match="not found in manifest") as exc_info:
        execute_phase(
            unknown_phase,
            manifest,
            _TASTE,
            tmp_path,
            live_dir,
            _make_artifacts(tmp_path),
            agent="codex",
            model="fake",
            effort="low",
            timeout=None,
            validation_command="true",
            max_attempts=1,
        )

    assert exc_info.value.__cause__ is None
    assert manifest_path.read_text(encoding="utf-8") == original


def test_execute_phase_retry_prompt_uses_sanitized_validation_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_dir = tmp_path / "live"
    manifest = _make_manifest()

    prompts: list[str] = []
    validation_calls = 0

    monkeypatch.setattr(
        "continuous_refactoring.phases.get_head_sha", lambda _: "abc123",
    )
    monkeypatch.setattr(
        "continuous_refactoring.phases.revert_to",
        lambda _repo, _head: None,
    )

    def fake_agent(**kwargs: object) -> CommandCapture:
        prompts.append(str(kwargs.get("prompt", "")))
        stdout_path = Path(str(kwargs["stdout_path"]))
        stderr_path = Path(str(kwargs["stderr_path"]))
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text("done\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return CommandCapture(
            command=("fake",),
            returncode=0,
            stdout="done\n",
            stderr="",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )

    def fail_with_noise_then_pass(
        test_command: str,
        repo_root: Path,
        stdout_path: Path,
        stderr_path: Path,
        **kwargs: object,
    ) -> CommandCapture:
        nonlocal validation_calls
        validation_calls += 1
        if validation_calls == 1:
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            stdout_path.write_text(
                "codex exec --model fake VERY-HUGE-PROMPT\nFOOBAR-MARKER failed\n",
                encoding="utf-8",
            )
            stderr_path.write_text("", encoding="utf-8")
            return CommandCapture(
                command=("pytest",),
                returncode=1,
                stdout=(
                    "codex exec --model fake VERY-HUGE-PROMPT\n"
                    "FOOBAR-MARKER failed\n"
                ),
                stderr="",
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
        return _passing_tests(test_command, repo_root, stdout_path, stderr_path)

    monkeypatch.setattr("continuous_refactoring.phases.maybe_run_agent", fake_agent)
    monkeypatch.setattr("continuous_refactoring.phases.run_tests", fail_with_noise_then_pass)

    outcome = execute_phase(
        _PHASE_0,
        manifest,
        _TASTE,
        tmp_path,
        live_dir,
        _make_artifacts(tmp_path),
        agent="codex",
        model="fake",
        effort="low",
        timeout=None,
        validation_command="true",
        max_attempts=2,
    )

    assert outcome.status == "done"
    assert len(prompts) == 2
    assert "## Retry Context" in prompts[1]
    assert "validation failed after phase execution" in prompts[1]
    assert "FOOBAR-MARKER" not in prompts[1]
    assert "VERY-HUGE-PROMPT" not in prompts[1]
