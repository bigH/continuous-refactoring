from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import continuous_refactoring.scope_expansion as scope_expansion
from continuous_refactoring.artifacts import (
    CommandCapture,
    ContinuousRefactorError,
    RunArtifacts,
    create_run_artifacts,
)
from continuous_refactoring.scope_candidates import ScopeCandidate, ScopeCandidateKind
from continuous_refactoring.scope_expansion import (
    ScopeSelection,
    select_scope_candidate,
    scope_candidate_to_target,
    scope_expansion_bypass_reason,
    write_scope_expansion_artifacts,
)
from continuous_refactoring.targeting import Target


def _candidate(kind: ScopeCandidateKind) -> ScopeCandidate:
    return ScopeCandidate(
        kind=kind,
        files=("README.md", "src/expanded.py"),
        cluster_labels=("README.md", "src"),
        evidence_lines=("seed target",),
        validation_surfaces=("README.md",),
    )


def _make_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunArtifacts:
    tmpdir = tmp_path / "tmpdir"
    tmpdir.mkdir(exist_ok=True)
    monkeypatch.setenv("TMPDIR", str(tmpdir))
    return create_run_artifacts(
        repo_root=tmp_path,
        agent="codex",
        model="fake",
        effort="low",
        test_command="true",
    )


def _fake_capture(stdout: str, tmp_path: Path, *, returncode: int = 0) -> CommandCapture:
    return CommandCapture(
        command=("fake",),
        returncode=returncode,
        stdout=stdout,
        stderr="",
        stdout_path=tmp_path / "stdout.log",
        stderr_path=tmp_path / "stderr.log",
    )


def _events(artifacts: RunArtifacts) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in artifacts.events_path.read_text(encoding="utf-8").splitlines()
    ]


def test_explicit_multi_file_targets_bypass_expansion() -> None:
    target = Target(
        description="explicit paths",
        files=("src/foo.py", "src/bar.py"),
        provenance="paths",
    )

    reason = scope_expansion_bypass_reason(target)

    assert reason == "scope expansion bypassed for explicit multi-file target"


def test_scope_candidate_to_target_replaces_target_files() -> None:
    target = Target(
        description="clean up",
        files=("src/foo.py",),
        provenance="globs",
    )
    candidate = _candidate("cross-cluster")

    selected = scope_candidate_to_target(target, candidate)

    assert selected == Target(
        description="clean up",
        files=("README.md", "src/expanded.py"),
        provenance="globs",
    )


def test_select_scope_candidate_single_candidate_writes_selection_logs(
    tmp_path: Path,
) -> None:
    target = Target(description="clean up", files=("README.md",), provenance="globs")
    candidate = _candidate("seed")
    artifacts = SimpleNamespace(root=tmp_path)

    selection = select_scope_candidate(
        target,
        (candidate,),
        "taste",
        tmp_path,
        artifacts,
        agent="codex",
        model="gpt-5.5",
        effort="low",
        timeout=None,
    )

    selection_dir = tmp_path / "scope-expansion"
    expected = "selected-candidate: seed — only viable candidate\n"
    assert selection == ScopeSelection(kind="seed", reason="only viable candidate")
    assert (selection_dir / "selection.stdout.log").read_text(encoding="utf-8") == expected
    assert (
        selection_dir / "selection-last-message.md"
    ).read_text(encoding="utf-8") == expected


def test_write_scope_expansion_artifacts_records_payload(tmp_path: Path) -> None:
    target = Target(description="clean up", files=("README.md",), provenance="globs")
    candidates = (_candidate("seed"), _candidate("local-cluster"))
    selection = ScopeSelection(kind="local-cluster", reason="clustered evidence")
    scope_dir = tmp_path / "scope-expansion"

    write_scope_expansion_artifacts(
        scope_dir,
        target,
        candidates,
        bypass_reason=None,
        selection=selection,
    )

    payload = json.loads((scope_dir / "variants.json").read_text(encoding="utf-8"))
    assert payload["target"] == {
        "description": "clean up",
        "files": ["README.md"],
        "provenance": "globs",
    }
    assert payload["bypass_reason"] is None
    assert len(payload["candidates"]) == 2
    assert payload["candidates"][0] == {
        "kind": "seed",
        "files": ["README.md", "src/expanded.py"],
        "cluster_labels": ["README.md", "src"],
        "evidence_lines": ["seed target"],
        "validation_surfaces": ["README.md"],
    }
    assert payload["selection"] == {"kind": "local-cluster", "reason": "clustered evidence"}


def test_select_scope_candidate_surfaces_parser_boundary_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = Target(description="clean up", files=("README.md",), provenance="globs")
    candidates = (_candidate("seed"), _candidate("local-cluster"))
    artifacts = _make_artifacts(tmp_path, monkeypatch)

    def fake_run_agent(**_: object) -> CommandCapture:
        return _fake_capture("pick local cluster\n", tmp_path)

    monkeypatch.setattr(scope_expansion, "maybe_run_agent", fake_run_agent)

    with pytest.raises(ContinuousRefactorError, match="unrecognised output"):
        select_scope_candidate(
            target,
            candidates,
            "taste",
            tmp_path,
            artifacts,
            agent="codex",
            model="gpt-5.5",
            effort="low",
            timeout=None,
        )

    failed = [
        event for event in _events(artifacts)
        if event.get("event") == "call_finished"
    ][-1]
    assert failed["call_role"] == "scope-expansion"
    assert failed["call_status"] == "failed"


def test_select_scope_candidate_multi_candidate_logs_call_events_with_effort(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = Target(description="clean up", files=("README.md",), provenance="globs")
    candidates = (_candidate("seed"), _candidate("local-cluster"))
    artifacts = _make_artifacts(tmp_path, monkeypatch)
    effort_metadata = {
        "effort_source": "target-override",
        "requested_effort": "xhigh",
        "effective_effort": "medium",
        "max_allowed_effort": "medium",
        "effort_capped": True,
        "effort_reason": "test cap",
    }

    def fake_run_agent(**kwargs: object) -> CommandCapture:
        for key in ("stdout_path", "stderr_path"):
            path = Path(str(kwargs[key]))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        return _fake_capture(
            "selected-candidate: local-cluster — clustered evidence\n",
            tmp_path,
        )

    monkeypatch.setattr(scope_expansion, "maybe_run_agent", fake_run_agent)

    selection = select_scope_candidate(
        target,
        candidates,
        "taste",
        tmp_path,
        artifacts,
        agent="codex",
        model="gpt-5.5",
        effort="medium",
        timeout=None,
        effort_metadata=effort_metadata,
    )

    assert selection == ScopeSelection(
        kind="local-cluster",
        reason="clustered evidence",
    )
    call_events = [
        event for event in _events(artifacts)
        if event.get("call_role") == "scope-expansion"
    ]
    assert [event["event"] for event in call_events] == [
        "call_started",
        "call_finished",
    ]
    assert [event["target"] for event in call_events] == ["clean up", "clean up"]
    assert call_events[1]["call_status"] == "finished"
    assert call_events[1]["returncode"] == 0
    for event in call_events:
        assert event["requested_effort"] == "xhigh"
        assert event["effective_effort"] == "medium"
        assert event["max_allowed_effort"] == "medium"
        assert event["effort_source"] == "target-override"
        assert event["effort_capped"] is True
