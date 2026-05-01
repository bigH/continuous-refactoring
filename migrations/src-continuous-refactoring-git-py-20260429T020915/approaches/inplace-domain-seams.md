# Approach: In-Place Domain Seams

## Strategy
- Keep `src/continuous_refactoring/git.py` as the public and internal home for git helpers.
- Reorganize the file around three clear sections:
  - subprocess boundary and error translation,
  - read-only repository state queries,
  - destructive worktree and history mutations.
- Add tests that lock the current behavior before moving helpers around, especially exact failure wrapping and destructive reset behavior.
- Tighten naming so call sites read in domain terms without introducing new modules or compatibility layers.

## Tradeoffs
- Safest option. Lowest risk to `loop.py`, `refactor_attempts.py`, `phases.py`, and package-root exports.
- Good fit if the real problem is that `git.py` reads like a junk drawer, not that its module boundary is wrong.
- Keeps one module owning both read and write git behavior.
- Leaves `run_command()` as a broad primitive shared across domains, which may still feel a little too generic.

## Estimated phases
1. Add characterization tests for `run_command()`, worktree status helpers, destructive reset helpers, and commit/revert flows.
   - `required_effort`: `low`
2. Refactor private helper flow so mutations share one obvious reset path and read-only helpers read top-down.
   - `required_effort`: `low`
3. Narrow error translation to the subprocess boundary and keep higher-level helpers bubbling signal unless they add domain context.
   - `required_effort`: `low`
4. Delete stale helper shapes, rerun `tests/test_git.py`, then full pytest.
   - `required_effort`: `low`

## Risk profile
- Technical risk: low
- Blast radius: low
- Failure modes:
  - Refactor changes exact error text that downstream tests assert.
  - Cleanup accidentally changes semantics around `git_commit()` no-op detection or destructive reset ordering.

## Best when
- We want the fastest safe readability win.
- We do not yet have evidence that a new module boundary will pay for itself.
