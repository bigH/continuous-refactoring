# Phase 3 — Release Pipeline Consistency Check

required_effort: low
effort_reason: This is a constrained alignment pass with change-only-if-mismatch policy.

## Scope
- `.github/workflows/release.yml`
- Any directly related release-smoke assertions/config lines required for consistency

## Objectives
- Confirm release workflow smoke assumptions align with locked CLI/module-entry contracts.
- Apply minimal workflow correction only if mismatch is identified.

## Precondition
- Phase 2 is complete.
- Phase 1 interface contracts remain the intended canonical behavior.
- Release workflow file exists and is readable in this checkout.
- Any planned workflow change is traceable to a concrete contract mismatch, not preference.

## Implementation Instructions
1. Compare release workflow smoke/entrypoint assumptions against Phase 1 contract tests.
2. If no mismatch exists, keep workflow unchanged and record no-op consistency confirmation in phase notes/commit context.
3. If mismatch exists, make smallest safe workflow edit to restore alignment.
4. Avoid broad CI restructuring or unrelated workflow cleanup.

## Validation Steps
1. Validate syntax/coherence of workflow edits (if any) with repository-standard checks.
2. Run the configured full validation command.

## Definition of Done
- Release workflow assumptions are confirmed consistent with locked interface contracts.
- Any workflow edit is minimal and directly justified by a discovered mismatch.
- No unrelated CI behavior changes were introduced.
- Configured full validation command passes.
