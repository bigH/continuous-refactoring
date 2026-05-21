Updated the migration planning artifacts in the staged work dir, using the chosen approach (`interface-first-hardening`) and addressing the review finding.

Created/updated:
- `plan.md`
- `phase-1-boundary-contract-guardrails.md`
- `phase-2-internal-effort-resolution-cleanup.md`
- `phase-3-pr-title-policy-adjustment-review-gated.md`

Key fix applied:
- In `phase-2-internal-effort-resolution-cleanup.md`, the precondition no longer requires tests to be “passing locally” (harness-owned baseline validation).  
- It now correctly uses a phase-local precondition: Phase 1 guardrail tests must still exist, while pass/fail remains in validation/Definition of Done.
