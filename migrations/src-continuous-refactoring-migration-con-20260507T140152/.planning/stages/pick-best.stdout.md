Chosen approach: **`incremental-validator-extraction`**

Why this is the best balance:
- **Lowest regression/interface risk** for a module that directly gates execution, publish, and doctor flows.
- **Highest incremental verifiability**: each phase is independently shippable and testable without policy rewrites.
- **Clarity gain now, policy risk later**: it improves structure and readability immediately while preserving current behavior and finding contracts.
- **Matches taste**: favors compatibility for shipped interfaces, avoids risky hard cuts, and keeps abstractions small and behavior-transparent.

Why not the others (short):
- `policy-table-normalization`: stronger long-term policy clarity, but higher chance of subtle gating drift in a sensitive boundary.
- `strict-contract-hardening`: valuable when intentionally changing guarantees, but too much behavior-change blast radius for this migration’s stated balance target.
