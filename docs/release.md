# Release Checklist

This project publishes as `continuous-refactoring` on PyPI.

Do not publish from a dirty tree, do not commit generated artifacts, and do not
tag or push unless that is the release task at hand.

## Before building

1. Confirm `pyproject.toml` metadata still matches the release.
2. Confirm `LICENSE` is present and `license = "MIT"` is still intentional.
3. Confirm the version is the intended release version.
4. Confirm the PyPI project name is still available if this is the first
   release.
5. Confirm PyPI Trusted Publishing is configured if publishing from CI.

## Build and inspect

```bash
uv run pytest
rm -rf dist
uv build
```

Inspect both artifacts before publishing:

```bash
uv run python -m zipfile -l dist/*.whl
uv run python -m tarfile -l dist/*.tar.gz
```

The wheel should contain only `continuous_refactoring/**` plus dist-info files.
The sdist should contain packaging metadata, `README.md`, `LICENSE`, `src/**`,
and `tests/**`. It must not contain `migrations/`, `approaches/`,
`.scratchpad/`, `.hiren/`, `AGENTS.md`, `CLAUDE.md`, `uv.lock`,
`.python-version`, `dist/`, or `build/`.

## Smoke test artifacts

Install each artifact into a fresh environment outside the checkout and confirm
the CLI starts:

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
    "$workdir/venv/bin/continuous-refactoring" --help
    "$workdir/venv/bin/python" -m continuous_refactoring --help
  )
done
```

## Publish

Preferred path: publish from the configured PyPI Trusted Publisher.

Local fallback, only when intentional:

```bash
uv publish
```

After publishing, verify the PyPI project page, then create any release tag or
GitHub release required by the release plan.
