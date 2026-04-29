# Release Management

This project publishes as `continuous-refactoring` on PyPI.

Release Please owns version bumps, `CHANGELOG.md`, `vX.Y.Z` tags, and GitHub
releases. Maintainers merge Release Please PRs; they do not hand-edit release
versions except for bootstrap or emergency repair.

PyPI publishing runs from GitHub Actions through Trusted Publishing. Do not use
PyPI API tokens for normal releases.

## Normal Flow

1. Land release-driving work through PRs into `main`.
2. Release Please opens or updates a release PR from conventional commits.
3. A maintainer reviews and merges the Release Please PR.
4. The `Release` workflow creates the GitHub release, builds distributions,
   runs tests, smoke-tests the wheel and sdist, uploads artifacts, and publishes
   to PyPI.

The implementation is bootstrapped from the existing `0.2.0` release via
`.release-please-manifest.json`. The config keeps tags as `vX.Y.Z`, without a
package component in the tag.

## Commit and PR Conventions

PR titles must match:

```bash
<type>(optional-scope)!: Capitalized Title Text
```

Allowed types: `feat`, `chore`, `fix`, `refactor`, `migration`. The scope and
`!` are optional.

Examples:

- `feat: Add Migration Planning`
- `fix: Preserve Taste Fallback`
- `refactor(scope): Simplify Target Routing`
- `feat!: Replace Migration Manifest Format`
- `chore: Release v0.2.1`

Release Please uses Conventional Commits as the source of truth for version
bumps:

- `feat:` produces a minor release.
- `fix:` produces a patch release.
- Breaking changes require `!` after the type or a `BREAKING CHANGE:` footer.
- `chore:` and `refactor:` are for non-release cleanup unless the change truly
  affects user behavior.

## Required GitHub and PyPI Settings

YAML cannot enforce these repository settings:

1. In GitHub branch protection or rulesets, require the `validate` status check
   from the `PR Title` workflow before merging to `main`.
2. Add a repository secret named `RELEASE_PLEASE_TOKEN` for Release Please. A
   fine-grained token needs Contents read/write and Pull requests read/write for
   `bigH/continuous-refactoring`. Without this secret, the workflow falls back
   to `GITHUB_TOKEN`, whose PRs do not trigger follow-on PR workflows.
3. In GitHub Settings > Actions > General, allow GitHub Actions to create pull
   requests if Release Please uses the `GITHUB_TOKEN` fallback.
4. In PyPI, configure a Trusted Publisher for:
   - owner: `bigH`
   - repository: `continuous-refactoring`
   - workflow: `release.yml`
   - environment: `pypi`
5. In GitHub Environments, configure the `pypi` environment. Required reviewers
   are recommended for publish approval.

## Manual Inspection

The release workflow does this automatically after Release Please creates a
release. For emergency local inspection only:

```bash
uv run pytest
rm -rf dist
uv build
uv run python -m zipfile -l dist/*.whl
uv run python -m tarfile -l dist/*.tar.gz
```

The wheel should contain only `continuous_refactoring/**` plus dist-info files.
The sdist should contain packaging metadata, `README.md`, `LICENSE`, `src/**`,
and `tests/**`. It must not contain `migrations/`, `approaches/`,
`.scratchpad/`, `.hiren/`, `AGENTS.md`, `CLAUDE.md`, `uv.lock`,
`.python-version`, `dist/`, or `build/`.

## Smoke Test Artifacts

Install each artifact into a fresh environment outside the checkout:

```bash
set -euo pipefail

wheel="$(python - <<'PY'
from pathlib import Path
print(next(Path("dist").glob("*.whl")).resolve())
PY
)"
sdist="$(python - <<'PY'
from pathlib import Path
print(next(Path("dist").glob("*.tar.gz")).resolve())
PY
)"

tmpdirs=()
cleanup() {
  rm -rf "${tmpdirs[@]}"
}
trap cleanup EXIT

for artifact in "$wheel" "$sdist"; do
  workdir="$(mktemp -d)"
  tmpdirs+=("$workdir")
  python -m venv "$workdir/venv"
  (
    cd "$workdir"
    "$workdir/venv/bin/python" -m pip install "$artifact"
    "$workdir/venv/bin/continuous-refactoring" --version
    "$workdir/venv/bin/python" -m continuous_refactoring --version
  )
done
```
