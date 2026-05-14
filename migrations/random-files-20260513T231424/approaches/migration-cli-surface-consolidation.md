# Migration CLI Surface Consolidation

## Strategy
Refactor `migration_cli.py` to consolidate argument/target validation, boundary error handling, and shared reporting paths while preserving command semantics (`list`, `doctor`, `review`, `refine`) and exit-code contracts.

## Why this path
- Current file mixes routing, I/O, and error-code policy in long paths.
- High value for readability and future command additions.
- Aligns with taste: domain-focused module boundaries and explicit interface risk surfacing.

## Tradeoffs
- Pros: clearer command-specific flows, less duplicated `try/except` scaffolding.
- Cons: CLI is user-facing; even tiny message/exit changes are review-sensitive.

## Estimated phases
1. Shared boundary helpers for CLI command execution
- Goal: centralize repeated resolve/load/exit translation patterns.
- Required effort: `low`
- Risk: medium

2. Target resolution and error message tightening
- Goal: keep current behavior but make ambiguous/invalid path handling easier to reason about and test.
- Required effort: `medium`
- Risk: medium

3. Doctor/list/refine output contract tests
- Goal: pin printed outputs and exit statuses for high-risk edge cases.
- Required effort: `medium`
- Risk: low

4. Optional release metadata touchpoint audit (`release-please-config.json`, `LICENSE`)
- Goal: verify no release-interface drift assumptions in CLI docs/messages; no behavior change.
- Required effort: `low`
- Risk: low

## Risk profile
- Overall risk: **medium**.
- Primary risks: accidental CLI output/exit drift that impacts scripts.
- Mitigations: golden-style CLI tests, keep public wording stable unless intentionally changed and flagged for review.

## Best fit when
You want a cleaner CLI core with limited algorithmic risk but accept interface-surface scrutiny.
