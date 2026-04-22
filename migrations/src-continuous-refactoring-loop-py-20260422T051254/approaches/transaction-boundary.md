# Transaction Boundary

## Strategy

Extract git rollback and commit-finalization behavior into a dedicated transaction boundary, then make both ordinary refactor attempts and migration ticks depend on that boundary.

Likely module: `src/continuous_refactoring/git_transaction.py`.

Owned behavior:
- capture `head_before`
- discard or revert failed work
- squash agent-created commits back into one driver commit
- record commits in artifacts
- expose small concrete operations such as `start_transaction()`, `revert_transaction()`, and `commit_transaction()`

The goal is not a generic transaction framework. The goal is to make the repo's most load-bearing invariant explicit: agents may edit and even commit, but the driver owns the final commit and failed attempts leave no workspace residue.

## Tradeoffs

Pros:
- Pulls a risky invariant into a named module with focused tests.
- Reduces duplicated `head_before`, `revert_to()`, `discard_workspace_changes()`, and `_finalize_commit()` choreography.
- Benefits both `loop.py` and `migration_tick.py`/`phases.py` because migration execution also relies on host-side validation and finalization.
- Makes future rollback bugs easier to diagnose.

Cons:
- Touches a broader set of modules than a `loop.py`-only cleanup.
- A poorly named abstraction could hide important git commands. The API must stay concrete.
- Existing tests heavily assert behavior through full runs; adding narrow transaction tests requires careful fake repos.
- It may be premature if the immediate pain is file length rather than commit semantics.

## Estimated Phases

1. **Strengthen transaction tests**
   - Add focused tests using real git repos for:
     - no changes means no commit
     - uncommitted edits are committed by the driver
     - agent-created commits are soft-reset and recommitted once
     - failed attempts hard-reset and clean untracked files
   - Keep assertions on git log and workspace status, not mocked git calls.

2. **Extract commit finalization**
   - Move `_finalize_commit()` behavior into `git_transaction.py`.
   - Update `loop.py`, `migration_tick.py`, and tests that monkeypatch `continuous_refactoring.loop._finalize_commit`.
   - Preserve artifact commit recording and printed `Committed: <sha>` output.

3. **Extract rollback helpers**
   - Replace scattered `get_head_sha()` plus `revert_to()` and `discard_workspace_changes()` pairs with concrete transaction helpers where doing so improves clarity.
   - Do not force every git operation through the new module; `git.py` remains the low-level command boundary.

4. **Retire obsolete comments**
   - The "runner owns the final commit" comment can disappear if the transaction API name says it.
   - Update `AGENTS.md` only if line references or described subtleties change.
   - Run `uv run pytest`.

## Risk Profile

Medium. The behavior is critical, but it can be validated well with real git repos and existing regression tests.

Main watch-outs:
- Preserve `git reset --soft head_before` for agent-created commits during successful finalization.
- Preserve hard reset plus clean for failed attempts.
- Keep exception wrapping at module boundaries. Low-level git failures should still surface as `ContinuousRefactorError` from `git.run_command()`.
- Update `AGENTS.md` if the driver-owned-commit subtlety moves out of `loop.py`.

## Best Fit

Choose this if the migration should protect the highest-risk behavior before shrinking `loop.py`. It is more architectural than the refactor-attempt extraction, but the invariant is important enough to justify a focused module.
