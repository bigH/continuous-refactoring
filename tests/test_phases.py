from __future__ import annotations

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
