1. `phase-2-refactor-local-control-flow.md` precondition conflates start gating with validation outcome: “Phase 1 focused tests exist and pass in the workspace.”  
   Why this is a finding: your rule explicitly says preconditions must not restate harness-owned/baseline-green style checks (including “tests pass now”). This should move to Validation/DoD, and the precondition should stay artifact/state-based (for example: “Phase 1 completed and its tests are present”).  

No other findings.
