# Discovery Module Extraction

## Strategy

Move pure candidate discovery out of `scope_expansion.py` into a domain-focused module, likely `src/continuous_refactoring/scope_candidates.py`.

The new module owns:
- `ScopeCandidate`
- `ScopeCandidateKind`
- `build_scope_candidates`
- candidate evidence helpers
- path aliasing, source/test pairing, reference scans, co-change scoring

`scope_expansion.py` becomes the orchestration boundary for:
- bypass decisions
- invoking the selection agent
- converting the selected candidate into a `Target`
- writing artifacts

Call sites and tests import moved symbols from their new home. No re-export shims.

## Tradeoffs

Pros:
- Stronger domain boundary: candidate discovery is pure-ish and testable without agent/artifact concerns.
- Reduces `scope_expansion.py` to the actual expansion workflow.
- Makes future scoring-rule changes easier to reason about.
- Gives meaningful FQNs instead of hiding all behavior behind `scope_expansion`.

Cons:
- Moderate churn: imports in `prompts.py`, tests, `routing_pipeline.py`, and `__init__.py` must move together.
- Public surface changes are direct. That matches the no-shim rule, but it is still a compatibility cut.
- `prompts.py` currently type-checks against `ScopeCandidate`; moving the type needs careful import-cycle handling.
- New module must be added to package re-export machinery without duplicate symbols.

## Estimated Phases

1. **Lock candidate behavior**
   - Broaden `tests/test_scope_expansion.py` or create `tests/test_scope_candidates.py` around pure discovery behavior.
   - Cover direct/reverse aliases, source/test pairing, co-change capping, local/cross pruning, and untracked seed fallback.

2. **Extract candidate module**
   - Move dataclasses, literals, and pure discovery helpers into `scope_candidates.py`.
   - Update all imports and monkeypatch targets in the same phase.
   - Update `src/continuous_refactoring/__init__.py` to include the new module and avoid duplicate exports.

3. **Slim orchestration module**
   - Keep `scope_expansion.py` focused on bypass, selection, target conversion, and artifacts.
   - Re-evaluate names after the split; remove helpers whose only purpose was compensating for module breadth.

4. **Validation and docs**
   - Run focused tests, then `uv run pytest`.
   - Update `AGENTS.md` only if scope-expansion vocabulary or load-bearing subtleties changed.

## Risk Profile

Medium risk. Behavior should be preservable, but import movement can break package boot because `__init__.py` enforces unique exported symbols.

Main watch-outs:
- No compatibility re-export from `scope_expansion.py`; update every caller directly.
- Avoid moving selection parser just because it is small. Parser behavior belongs closer to selection-agent I/O than candidate discovery.
- Keep the new module stdlib-only and flat; no subpackage.

## Best Fit

Choose this if the migration's real aim is to make candidate discovery independently understandable and easier to evolve. This is the cleanest structural split, but it is not the lowest-risk path.
