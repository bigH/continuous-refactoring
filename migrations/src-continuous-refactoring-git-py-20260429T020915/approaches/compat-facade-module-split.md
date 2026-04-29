# Approach: Compatibility Facade Module Split

## Strategy
- Keep `src/continuous_refactoring/git.py` as the stable exported facade, but move implementation into internal modules with tighter domain focus.
- A sensible split here is:
  - `git.py`: public compatibility exports only,
  - `git_process.py`: subprocess execution and `GitCommandError`,
  - `git_worktree.py`: status queries, resets, revert, commit helpers.
- Update internal callers gradually where direct imports improve readability, while preserving existing `continuous_refactoring.git` imports and package-root exports.
- Treat any public export change as human-review territory and avoid it unless the migration explicitly chooses that break.

## Tradeoffs
- Stronger long-term shape without forcing a user-facing import migration now.
- Makes the subprocess boundary explicit and easier to test in isolation.
- More churn than in-place cleanup because imports move across several hot modules.
- Risks wrapper soup if `git.py` becomes a thin file full of mechanical pass-throughs instead of a meaningful facade.

## Estimated phases
1. Add regression tests around the current `continuous_refactoring.git` surface, including package-root availability through `continuous_refactoring`.
   - `required_effort`: `low`
2. Introduce `git_process.py` for command execution and boundary error wrapping, with behavior preserved exactly.
   - `required_effort`: `medium`
3. Introduce `git_worktree.py` for repo state and mutation helpers; re-export from `git.py`.
   - `required_effort`: `medium`
4. Redirect internal callers to the sharper modules only where it improves call-site clarity, then trim dead private glue.
   - `required_effort`: `medium`
5. Run full pytest and confirm package export uniqueness still holds.
   - `required_effort`: `low`

## Risk profile
- Technical risk: medium
- Blast radius: medium
- Failure modes:
  - Circular imports with `__init__.py` package export collection if the split is done mechanically.
  - Public-surface drift if `git.py` forgets to re-export a helper that tests do not cover.
  - Internal callers start mixing facade and direct-module imports in a way that gets less clear, not more.

## Best when
- We want cleaner boundaries now but do not want to break existing imports.
- We expect more git-related behavior to grow and want room without bloating one file further.
