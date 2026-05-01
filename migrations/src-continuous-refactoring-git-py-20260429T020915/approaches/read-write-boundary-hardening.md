# Approach: Read/Write Boundary Hardening

## Strategy
- Split git behavior by safety profile rather than by implementation detail:
  - read-only repository inspection,
  - destructive workspace/history mutation.
- Make read helpers pure-ish wrappers over git output and push destructive helpers behind a smaller, more explicit API.
- Use the migration to harden contracts at call sites: modules that only need inspection should stop importing mutation helpers.
- Keep compatibility for shipped imports only as long as needed for the migration, then aggressively delete dead compatibility if the project decides the sharper boundary is worth the churn.

## Tradeoffs
- Best architectural payoff. The dangerous operations stop hiding beside harmless queries.
- Improves reasoning in `loop.py`, `phases.py`, and `refactor_attempts.py` because each call site declares whether it is inspecting or mutating repo state.
- Highest churn of these options. More call-site edits, more chances to nick behavior.
- Most likely to surface human-review-worthy questions if any public helper moves or disappears.

## Estimated phases
1. Expand tests to distinguish read-only helpers from destructive helpers, including revert/reset invariants and branch-preservation expectations.
   - `required_effort`: `low`
2. Extract read-only helpers into a focused module such as `git_inspect.py` and redirect non-mutating callers.
   - `required_effort`: `medium`
3. Extract destructive helpers into a focused module such as `git_mutations.py`, then tighten helper names around intent rather than git verbs.
   - `required_effort`: `high`
4. Decide whether `git.py` remains a compatibility facade or is reduced/retired; require human review if package-visible behavior changes.
   - `required_effort`: `high`
5. Run full pytest and audit remaining imports for boundary violations or stale shims.
   - `required_effort`: `medium`

## Risk profile
- Technical risk: medium-high
- Blast radius: high
- Failure modes:
  - Call-site churn accidentally changes destructive sequencing, especially around reset/clean and commit finalization.
  - Compatibility cleanup breaks package-root imports or external expectations without enough review.
  - The split overfits today's call sites and leaves awkward names if future git behavior grows differently.

## Best when
- We want the cleanest domain boundary, not just a tidier file.
- We are willing to spend migration budget now to make destructive git behavior much more explicit.
