# Migration Plan: Split `loop.py` by Domain

**Target:** `src/continuous_refactoring/loop.py` (1646 lines)
**Chosen approach:** `split-by-domain`
**Current landed state after rollback:** phase 1 (`decisions.py`) is still present in the repo. Phases 2–4 were reverted: `failure_report.py` and `routing_pipeline.py` do not exist, the corresponding helpers still live in `loop.py`, and the affected tests still monkeypatch `continuous_refactoring.loop` for those symbols.
**Near-term goal shape:** finish the remaining extractions (`failure_report.py`, `routing_pipeline.py`) and then do a no-new-extraction tidy pass in `loop.py`. That scope should leave `loop.py` roughly **950–1100 lines**, not ~500.
**Stretch goal:** getting `loop.py` near ~500 lines needs a later migration with additional extraction scope (most likely `_run_refactor_attempt`, retry/commit plumbing, or the top-level loop orchestration). Phase 4 does **not** include that work.

Each phase is a single commit / single PR, leaves the repo shippable, and is validated by the existing test suite plus the normal CLI import/help checks. No flags, no shims, no re-exports.

## Ordering Rationale

Phases still move from lower-risk extraction to more entangled orchestration, but the hard dependencies are narrower than the original draft implied:

1. **decisions** — pure types + parsing. Already landed. It established the stable FQNs used by later phases.
2. **failure_report** — filesystem writes plus artifact persistence. Smaller than the routing move and a good first post-rollback restart point.
3. **routing_pipeline** — routing, migration-tick, and scope-expansion glue. Technically depends on phase 1, not on phase 2, but it stays after phase 2 in this plan because that keeps the restart sequence small and easy to review.
4. **trim loop.py** — cleanup only after phases 2 and 3 are both green. No new extraction in this phase.

## Dependency Graph

```text
phase-1 (decisions)
   ├──► phase-2 (failure_report)
   └──► phase-3 (routing_pipeline)

phase-2 + phase-3 ──► phase-4 (trim loop.py)
```

The manifest still advances in numeric order, so after this rollback `current_phase` should remain `failure-report` until phase 2 lands again.

## Cross-Cutting Concerns

- **Test monkeypatch paths reverted with the code.** Today the routing/failure-report tests still patch `continuous_refactoring.loop.*`. When phases 2 or 3 land, update the corresponding monkeypatch targets and imports in the same commit. The main files to grep are `tests/test_scope_loop_integration.py`, `tests/test_loop_migration_tick.py`, `tests/test_focus_on_live_migrations.py`, `tests/test_no_driver_branching.py`, and routing-related cases in `tests/test_run.py`.
- **No re-export shims.** If a symbol moves out of `loop.py`, every call site and every test monkeypatch target must move to the new FQN in the same commit.
- **Avoid circular imports.** Phase 3 must not import private helpers back from `loop.py`. If the extracted routing helpers still need data such as the resolved live-migrations dir or a commit finalizer, pass those in from `loop.py` or define local helpers inside `routing_pipeline.py`.
- **Naming.** Keep concrete module names: `decisions`, `failure_report`, `routing_pipeline`. No `utils`, `helpers`, `common`.

## Validation Strategy

Every phase must pass:
1. `uv run pytest`
2. `python -m continuous_refactoring --help`
3. Grep checks showing no remaining references to the old `continuous_refactoring.loop.<symbol>` FQN for the symbols moved in that phase.
4. `wc -l` sanity checks with realistic expectations for the phase's allowed scope.

Expected size ranges after the remaining work:
- `decisions.py`: already landed at ~205 lines.
- `failure_report.py`: roughly 170–260 lines.
- `routing_pipeline.py`: roughly 350–500 lines.
- `loop.py` after phases 2–4: roughly 950–1100 lines.

If the project still wants `loop.py` near ~500 after this migration, capture that as a follow-up extraction instead of stretching phase 3 or 4 beyond their stated scope.

## Shippability Invariant

After every phase:
- `cli.py` → `loop.py` imports still work.
- `run_once`, `run_loop`, and `run_migrations_focused_loop` keep the same behavior.
- The full test suite is green on the phase head commit.
- No symbol is defined in two places simultaneously.

## Quality Bar

- No new comments unless a non-obvious invariant demands one.
- No speculative interfaces. Concrete modules only.
- Delete stale imports and old monkeypatch targets in the same commit as the move.
- Do not claim a size reduction the phase cannot realistically achieve.

## Phases

| # | Name | File | Blockers |
|---|------|------|----------|
| 1 | Extract `decisions` | `phase-1-decisions.md` | none |
| 2 | Extract `failure_report` | `phase-2-failure-report.md` | phase 1 |
| 3 | Extract `routing_pipeline` | `phase-3-routing-pipeline.md` | phase 1 |
| 4 | Trim `loop.py` | `phase-4-trim-loop.md` | phases 2, 3 |
