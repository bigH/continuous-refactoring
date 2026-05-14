# Boundary Hardening First

## Strategy
Tighten module-boundary error translation and role-specific failure mapping across `routing_pipeline.py`, `phases.py`, and `migration_cli.py` without changing external CLI contracts or migration file formats. Keep behavior stable, make failure paths more explicit, and reduce ambiguous `abandon/blocked` classification drift.

## Why this path
- Lowest blast radius while improving correctness in load-bearing paths.
- Matches taste: translate at boundaries, not internally; avoid speculative abstractions.
- Preserves human-review-sensitive interfaces (CLI behavior, manifest/state structures).

## Tradeoffs
- Pros: safer rollout, easier review, minimal user-visible change.
- Cons: does not materially simplify orchestration shape; some duplication may remain.

## Estimated phases
1. Failure taxonomy alignment (`routing_pipeline.py`, `phases.py`)
- Goal: unify mapping from exceptions/results to `failure_kind` + route outcome with explicit helpers.
- Required effort: `low`
- Risk: low

2. CLI boundary normalization (`migration_cli.py`)
- Goal: centralize `SystemExit` code decisions and boundary wrapping for read/resolve/refine flows.
- Required effort: `medium`
- Risk: medium (CLI-facing)

3. Regression proofing (tests around unchanged contracts)
- Goal: strengthen example-based tests for failure mode outputs and exit codes.
- Required effort: `medium`
- Risk: low

## Risk profile
- Overall risk: **low**.
- Primary risk: accidental CLI message/exit-code drift.
- Mitigations: keep string contracts stable where intentionally user-facing; assert outputs in tests.

## Best fit when
You want immediate reliability gains with minimal behavior change and fast merge confidence.
