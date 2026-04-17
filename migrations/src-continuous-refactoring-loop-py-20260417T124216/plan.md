# Migration Plan: Split `loop.py` by Domain

**Target:** `src/continuous_refactoring/loop.py` (1656 lines)
**Chosen approach:** `split-by-domain`
**Goal shape:** `loop.py` ~500 lines; new modules `decisions.py`, `failure_report.py`, `routing_pipeline.py` each 200–400 lines.

Each phase is a single commit / single PR, leaves the repo shippable, and is validated by the existing test suite plus a `run-once` smoke. No flags, no shims, no re-exports — taste says delete legacy aggressively in non-shipped projects.

## Ordering Rationale

Phases progress from purest (no side effects, no deps) to most entangled (orchestration glue). Earlier phases de-risk later ones:

1. **decisions** — pure types + parsing. Zero imports from siblings. Lowest risk. Earns property-based tests that harden the status parser and YAML scalar escaping before anything else depends on them.
2. **failure_report** — filesystem writes; imports `decisions`. Depends on phase 1 landing so the types it consumes are already stable at their new FQN.
3. **routing_pipeline** — imports `decisions` + `failure_report`. Moves the largest single chunk (~400 lines) but only after its dependencies are in their final homes.
4. **trim loop.py** — delete dead imports, tidy ordering, verify `run_once`/`run_loop` read top-to-bottom. Pure cleanup; only runs after the three extractions are green.

## Dependency Graph

```
phase-1 (decisions)
   │
   ▼
phase-2 (failure_report) ──► depends on phase-1
   │
   ▼
phase-3 (routing_pipeline) ──► depends on phase-1, phase-2
   │
   ▼
phase-4 (trim loop.py) ──► depends on phase-3
```

Strictly sequential. No parallelism — each phase shifts import surfaces the next will touch.

## Cross-Cutting Concerns

- **Test monkeypatch paths.** Tests currently patch `continuous_refactoring.loop.<symbol>` (see `tests/conftest.py`, `tests/test_run_once.py`, `tests/test_loop_migration_tick.py`). Each phase must update monkeypatch targets to the new FQN. No re-export shims in `loop.py` — taste forbids backwards-compat hacks in this codebase.
- **Public API.** `cli.py` imports only `run_once`, `run_loop` from `loop`. That import stays intact across all phases.
- **Private helpers moving modules.** Where a private helper becomes the new module's public surface, drop the leading underscore (e.g., `_write_reason_for_failure` → `failure_report.write`, `_parse_agent_status_block` → `decisions.parse_status_block`). Inside-module helpers keep the underscore.
- **Naming.** Follow taste — meaningful FQNs. `decisions.AgentStatus`, `failure_report.write`, `routing_pipeline.route_and_run`. Avoid `utils`, `helpers`, `common`.

## Validation Strategy

Every phase must pass:
1. `pytest` — full suite green.
2. `python -m continuous_refactoring --help` loads without import errors.
3. A grep check: no remaining references to the old FQN of any moved symbol.
4. `git diff --stat` sanity — net line count drops from `loop.py` by the expected range; new module size within 200–400 lines.

Phase-specific checks are in each `phase-<n>-<name>.md`.

Property-based tests are added where the domain shape is pure:
- `decisions`: round-trip / invariants for `parse_status_block`; escaping invariants for YAML scalar rendering (phase 1 owns the `_yaml_scalar` tests even though the function itself moves to `failure_report` in phase 2 — it's pure and belongs in the earlier, safer phase for testing, then re-homes with its caller).

Correction: keep `_yaml_scalar` tests co-located with its module. Add them in phase 2.

## Shippability Invariant

After every phase:
- `cli.py` → `loop.py` import works.
- `run_once` and `run_loop` behavior unchanged.
- Test suite green on the phase's HEAD commit.
- No symbol is defined in two places simultaneously (no transitional shims).

## Quality Bar

- No new comments unless a non-obvious invariant demands one.
- No speculative interfaces. Concrete modules only.
- Delete `from .loop import ...` lines that become unused.
- Each PR description includes a Mermaid diagram of the modules touched.

## Phases

| # | Name | File | Blockers |
|---|------|------|----------|
| 1 | Extract `decisions` | `phase-1-decisions.md` | none |
| 2 | Extract `failure_report` | `phase-2-failure-report.md` | phase 1 |
| 3 | Extract `routing_pipeline` | `phase-3-routing-pipeline.md` | phases 1, 2 |
| 4 | Trim `loop.py` | `phase-4-trim-loop.md` | phase 3 |
