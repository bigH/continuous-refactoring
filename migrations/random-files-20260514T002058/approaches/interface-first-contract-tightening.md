# Interface-First Contract Tightening

## Strategy
Prioritize explicit interface guarantees first (`__main__`, `--version`, routing decision parsing), then align tests and docs around those boundaries before touching any adjacent cleanup.

## Why this path
- Lowest behavior-risk for shipped CLI surfaces.
- Matches taste guidance: treat CLI behavior and repo-written interactions as human-review territory.
- Lets us delete ambiguity in tests without broad structural change.

## Estimated phases
1. **Phase: Freeze interface contracts**
- Scope: `src/continuous_refactoring/__main__.py`, `tests/test_cli_version.py`, `tests/test_routing.py`
- Work: codify expected `python -m continuous_refactoring` and `--version` behavior; tighten routing parse/error invariants at module boundary.
- `required_effort`: `low`

2. **Phase: Boundary-focused cleanup**
- Scope: `src/continuous_refactoring/routing.py` (+ tests)
- Work: small abstraction passes only where they reduce repetition in classify error logging/parsing; preserve exception nesting and call-finished semantics.
- `required_effort`: `medium`

3. **Phase: Release pipeline consistency check**
- Scope: `.github/workflows/release.yml`
- Work: verify smoke-test assumptions still match CLI/module entrypoint contract; adjust only if mismatch exists.
- `required_effort`: `low`

## Tradeoffs
- Pros: safe rollout, clear review story, minimal blast radius.
- Cons: leaves larger stylistic cleanup opportunities on the table.

## Risk profile
- Overall risk: **Low**.
- Main risk: accidental drift in observable CLI/version output strings.
- Mitigation: exact-output tests stay canonical; avoid changes to output formatting unless intentionally reviewed.
