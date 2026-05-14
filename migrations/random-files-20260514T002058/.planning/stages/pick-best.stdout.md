**Choice:** `interface-first-contract-tightening`

**Why this wins**
- Best risk/clarity tradeoff: it starts by locking shipped interfaces (`python -m`, `--version`) before internal cleanup.
- Most incrementally verifiable: each phase has a clean testable boundary, then optional workflow alignment check at the end.
- Strongest taste fit: it explicitly treats released CLI behavior as human-review territory, preserves boundary exception behavior, and avoids speculative structural work.

**Why not the others**
- `release-smoke-alignment`: useful, but starts in workflow land where small mistakes can have outsized blast radius; weaker first step for a refactor migration.
- `routing-parser-hardening`: technically solid and contained, but it underweights explicit CLI contract hardening, which is the higher-risk external boundary in this repo.

**Effort profile sanity**
- Proposed phase efforts (`low`, `medium`, `low`) are the lowest safe levels and stay within current `xhigh` cap.
