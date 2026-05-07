Chosen approach: **`minimal-rationale-hardening`**

Why this is the best balance now:
- **Lowest risk for shipped behavior**: `commit_messages.py` affects user-visible commit text, so keeping contract and ownership stable is the safest compatibility path.
- **Clear incremental verification**: test-first, then local control-flow cleanup, then focused/full validation is a clean, reversible sequence.
- **Fits effort budget cleanly**: all phases can run at `low`, so no scheduling stalls behind higher-effort gates.
- **Taste tie-break**: this approach favors readability improvements without speculative abstraction or boundary reshaping, and avoids unnecessary interface movement across modules.

Runners-up:
- `policy-extraction-and-pure-rules`: good readability upside, but medium-risk policy reorder errors and medium effort are unnecessary for this migration scope.
- `shared-status-text-policy-consolidation`: strongest long-term cleanup, but blast radius and behavior-drift risk are too high for this refactor target.
