from __future__ import annotations

from itertools import combinations

import pytest

from continuous_refactoring.prompts import compose_scope_selection_prompt
from continuous_refactoring.scope_candidates import ScopeCandidate, ScopeCandidateKind
from continuous_refactoring.targeting import Target


_ALL_KINDS: tuple[ScopeCandidateKind, ...] = ("seed", "local-cluster", "cross-cluster")
_TASTE = "- Prefer deletion over wrapping.\n- Fail fast at boundaries."


def _target() -> Target:
    return Target(
        description="Clean up progress module",
        files=("packages/core/src/core/__tests__/progress.test.ts",),
        provenance="globs",
    )


def _candidate(kind: ScopeCandidateKind) -> ScopeCandidate:
    seed = "packages/core/src/core/__tests__/progress.test.ts"
    if kind == "seed":
        files = (seed,)
    elif kind == "local-cluster":
        files = (seed, "packages/core/src/core/progress.ts")
    else:
        files = (seed, "packages/app/src/progress-view.ts")
    return ScopeCandidate(
        kind=kind,
        files=files,
        cluster_labels=tuple(sorted({"/".join(f.split("/")[:-1]) for f in files})),
        evidence_lines=("seed target",),
        validation_surfaces=(seed,),
    )


def _candidates(kinds: tuple[ScopeCandidateKind, ...]) -> tuple[ScopeCandidate, ...]:
    return tuple(_candidate(kind) for kind in kinds)


def _contract_section(prompt: str) -> str:
    _, _, after = prompt.partition("## Output Contract")
    return after


def _prefer_section(prompt: str) -> str:
    _, _, after = prompt.partition("Prefer:")
    before, _, _ = after.partition("## Output Contract")
    return before


def test_prompt_lists_all_kinds_when_all_present() -> None:
    prompt = compose_scope_selection_prompt(_target(), _candidates(_ALL_KINDS), _TASTE)

    contract = _contract_section(prompt)
    prefer = _prefer_section(prompt)
    for kind in _ALL_KINDS:
        assert f"selected-candidate: {kind} \u2014 <short reason>" in contract
        assert f"`{kind}`" in prefer


def test_prompt_hides_pruned_kind_in_contract_and_prefer() -> None:
    kinds: tuple[ScopeCandidateKind, ...] = ("seed", "cross-cluster")
    prompt = compose_scope_selection_prompt(_target(), _candidates(kinds), _TASTE)

    contract = _contract_section(prompt)
    prefer = _prefer_section(prompt)
    assert "local-cluster" not in contract
    assert "local-cluster" not in prefer
    for kind in kinds:
        assert f"selected-candidate: {kind} \u2014 <short reason>" in contract
        assert f"`{kind}`" in prefer


def test_prompt_is_well_formed_with_single_kind() -> None:
    prompt = compose_scope_selection_prompt(_target(), _candidates(("seed",)), _TASTE)

    contract = _contract_section(prompt)
    assert "selected-candidate: seed \u2014 <short reason>" in contract
    for absent in ("local-cluster", "cross-cluster"):
        assert absent not in contract
    assert "## Taste" in prompt


@pytest.mark.parametrize(
    "kinds",
    [
        subset
        for size in (2, 3)
        for subset in combinations(_ALL_KINDS, size)
    ],
)
def test_contract_has_exactly_one_line_per_present_kind(
    kinds: tuple[ScopeCandidateKind, ...],
) -> None:
    prompt = compose_scope_selection_prompt(_target(), _candidates(kinds), _TASTE)

    contract = _contract_section(prompt)
    prefer = _prefer_section(prompt)
    present = set(kinds)
    for kind in _ALL_KINDS:
        sample_line = f"selected-candidate: {kind} \u2014 <short reason>"
        if kind in present:
            assert contract.count(sample_line) == 1
            assert f"`{kind}`" in prefer
        else:
            assert contract.count(sample_line) == 0
            assert f"`{kind}`" not in prefer


def test_prompt_deduplicates_repeated_candidate_kinds() -> None:
    prompt = compose_scope_selection_prompt(
        _target(),
        _candidates(("seed", "seed", "local-cluster")),
        _TASTE,
    )

    contract = _contract_section(prompt)
    prefer = _prefer_section(prompt)
    assert contract.count("selected-candidate: seed \u2014 <short reason>") == 1
    assert prefer.count("`seed`") == 1


def test_prompt_preserves_taste_section() -> None:
    prompt = compose_scope_selection_prompt(_target(), _candidates(_ALL_KINDS), _TASTE)

    assert f"## Taste\n{_TASTE}" in prompt
