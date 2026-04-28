from __future__ import annotations

import json
from pathlib import Path

from continuous_refactoring.scope_candidates import ScopeCandidate, ScopeCandidateKind
from continuous_refactoring.scope_expansion import (
    ScopeSelection,
    describe_scope_candidate,
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


def test_describe_scope_candidate_returns_readable_block() -> None:
    candidate = _candidate("local-cluster")

    formatted = describe_scope_candidate(candidate)

    assert formatted.startswith("Selected scope candidate: local-cluster")
    assert "- README.md" in formatted
    assert "- src/expanded.py" in formatted


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
    assert payload["selection"] == {"kind": "local-cluster", "reason": "clustered evidence"}
