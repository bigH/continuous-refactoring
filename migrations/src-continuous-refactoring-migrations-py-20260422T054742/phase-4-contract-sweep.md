# Phase 4: Contract Sweep

## Objective

Finish the extraction by making the new boundary intentional: no stale helpers, no accidental root exports, no drift in repo guidance, and no hidden call-site breakage.

## Precondition

Phase 3 is complete: `load_manifest()` and `save_manifest()` wrap low-level JSON and filesystem failures with preserved causes, codec schema failures are not double wrapped, atomic write cleanup still holds, manifest compatibility is unchanged, and all Phase 3 validation commands pass.

## Scope

Allowed production files:

- `src/continuous_refactoring/migrations.py`
- `src/continuous_refactoring/migration_manifest_codec.py`
- `src/continuous_refactoring/__init__.py` only to add or preserve tests against accidental export churn
- `AGENTS.md` only if the new codec boundary creates or changes a load-bearing repo invariant

Allowed test files:

- `tests/test_migrations.py`
- `tests/test_continuous_refactoring.py`
- focused call-site tests only if a call-site import was touched

Do not move scheduling, phase execution, planning, prompt formatting, CLI review behavior, or wake-up policy in this phase.

## Instructions

1. Inspect `migrations.py`.
   - Remove imports no longer needed after extraction, such as `asdict` if encoding moved fully.
   - Remove private schema helpers that now live in the codec.
   - Keep migration behavior helpers local and clearly named.
   - Keep comments near zero; preserve only section markers that aid navigation.
2. Inspect `migration_manifest_codec.py`.
   - Keep the module focused on payload decode/encode.
   - Keep helper names about manifest payloads and fields, not filesystem behavior.
   - Avoid speculative interfaces or context objects.
   - Ensure no helper reaches into path, wake-up, planning, phase execution, or prompt concerns.
3. Verify package import behavior.
   - `import continuous_refactoring` succeeds.
   - `from continuous_refactoring.migrations import MigrationManifest, PhaseSpec, load_manifest, save_manifest` succeeds.
   - `import continuous_refactoring.migration_manifest_codec` succeeds.
   - `continuous_refactoring` does not expose `decode_manifest_payload` or `encode_manifest_payload` at the package root.
   - `migration_manifest_codec` is not listed in `_SUBMODULES`.
4. Search for stale moved helper names and stale assumptions:
   - `_require_status`
   - `_require_phase`
   - `_require_phases`
   - `_require_current_phase`
   - `_legacy_current_phase_name`
   - `_require_unique_phase_names`
   - direct references to codec helpers from modules other than tests and `migrations.py`
5. Check repo guidance.
   - If `AGENTS.md` still implies `migrations.py` alone owns manifest wire-format compatibility, update it tightly.
   - If adding guidance, prefer one load-bearing note naming `migration_manifest_codec.py` as the owner of legacy `ready_when`, legacy integer `current_phase`, duplicate phase-name rejection, and saved JSON formatting.
   - Do not add broad process prose.
6. Do not start the runner-up module split work. If manifest domain types or scheduling policy now want their own home, leave that as a follow-up note in the phase result rather than moving them.

## Definition of Done

- `migrations.py` is smaller and owns migration behavior, not manifest payload schema plumbing.
- `migration_manifest_codec.py` owns only manifest payload decode/encode compatibility.
- Package-root exports are unchanged.
- No stale moved helpers remain in production.
- Repo guidance is not stale about the new manifest codec boundary.
- The full pytest gate passes.
- The repository is shippable after this phase.

## Validation

Run:

```sh
uv run pytest tests/test_migrations.py
uv run pytest tests/test_continuous_refactoring.py
uv run pytest tests/test_planning.py tests/test_phases.py tests/test_loop_migration_tick.py tests/test_prompts.py tests/test_cli_review.py
uv run pytest
```
