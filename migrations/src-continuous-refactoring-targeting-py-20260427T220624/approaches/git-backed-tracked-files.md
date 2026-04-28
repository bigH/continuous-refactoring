# Move Tracked-File Enumeration to `git.py`

## Strategy

Extract low-level repo access from `targeting.py` into `git.py` so file enumeration is centralized and boundary-faithful.

Proposed changes:
- Add `list_tracked_files(repo_root: Path) -> list[str]` to `src/continuous_refactoring/git.py` using existing `run_command`.
- Replace direct `subprocess.run([... "git", "ls-files", "-z"])` in `targeting.py` with `continuous_refactoring.git.list_tracked_files`.
- Keep `select_random_files` in `targeting.py` as policy (`count`, tuple return, ordering behavior) and use `git.py` only for repository access.
- Preserve warning/error behavior by preserving command output messages and wrapping failures with nested `ContinuousRefactorError` in one place.
- Add regression tests in both modules:
  - low-level git command edge cases (`git.py`) and
  - target resolution behavior under non-ASCII and empty-repo conditions (`test_targeting.py`).

This is explicitly non-speculative: there is real duplication pressure across modules that already depend on git command semantics.

## Tradeoffs

Pros:
- Stronger domain split around repository transport.
- Easier to test and mock repository behavior in one place.
- Improves consistency if other modules later need reliable tracked-file access.

Cons:
- Requires modifying `git.py`, which increases blast radius into `loop.py`, `artifacts.py`, and related tests through callsite imports.
- Need to keep error messages stable for existing tests that assert on command failure paths.
- Not as immediate a cleanup as pure in-place refactor.

## Estimated Phases

1. Git utility extraction
- Add `list_tracked_files` to `git.py` and test it with fixtures already used by `tests/test_git.py`.
- Keep interface narrow and stdlib-only.

2. Targeting integration
- Replace in-module git listing with the new utility.
- Ensure `select_random_files` and `expand_patterns_to_files` remain deterministic and deduplicated.

3. Scope and loop checks
- Update any callsites that need direct visibility of tracked-file listing behavior.
- Keep `targeting.py` API and `Target` contract unchanged.

4. Full behavioral pass
- Focused tests: `uv run pytest tests/test_git.py tests/test_targeting.py`
- Broader: `uv run pytest tests/test_run_once_regression.py tests/test_cli_init_taste.py`.

## Risk Profile

Medium.

Watch-outs:
- Avoid introducing temporary migration flags in CLI or runtime flow.
- Do not change fallback semantics: no random target shape change, no precedence change.
- Keep exception boundaries clear: `run_command` wraps low-level process issues, `targeting.py` wraps domain-level failures only.

