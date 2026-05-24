# AGENTS.md

## 1. Identity

Test-gated refactor loop that drives `codex` and `claude` CLIs through small, validated commits. Zero runtime deps, stdlib only. Dog-foods itself through live migrations. User-facing docs live in `README.md`; this file is the mutator's contract.

## 2. Keep this file current

Every agent working in this repo **MUST**:
- Update `AGENTS.md` in the same commit as any change that contradicts a statement here. Stale is worse than missing.
- Remove entries describing load-bearing subtleties that get refactored away.
- Add entries for new load-bearing subtleties, new migrations, new commands, new gotchas.

Treat `AGENTS.md` as part of the codebase's invariants, not documentation. A drift between this file and the code is a shipped bug.

## 3. Commands

- Install: `uv sync && uv pip install -e .`
- Test all: `uv run pytest`
- Test one: `uv run pytest tests/test_x.py::test_name`
- Entry: `continuous-refactoring --help` / `continuous-refactoring --version`
  (or `python -m continuous_refactoring`)
- Init: `continuous-refactoring init [--path PATH]
  [--live-migrations-dir DIR] [--in-repo-taste [PATH]] [--force]`
- Taste: `continuous-refactoring taste [--global]
  [--interview|--upgrade|--refine]
  [--with codex|claude --model <model>]
  [--force]`
  Active taste agent modes require `--with` and `--model`; the taste agent
  always runs at fixed `medium` effort.
- Run once: `continuous-refactoring run-once --with codex|claude
  --model <model> [common targeting/validation flags]`
- Run loop: `continuous-refactoring run --with codex|claude --model <model>
  [--max-attempts N] [--max-refactors N] [--focus-on-live-migrations]
  [--commit-message-prefix TEXT] [--max-consecutive-failures N] [--sleep N]`
  Requires targeting flags or `--scope-instruction` unless
  `--focus-on-live-migrations`; `--max-refactors` is required unless using
  `--targets` or `--focus-on-live-migrations`.
- Upgrade config: `continuous-refactoring upgrade`
- Inspect migrations: `continuous-refactoring migration list
  [--status planning|ready|in-progress|skipped|done]
  [--awaiting-review] [--no-headers]` /
  `continuous-refactoring migration doctor <slug-or-path>` /
  `continuous-refactoring migration doctor --all`
- Review migrations: `continuous-refactoring migration review <slug-or-path>
  --with codex|claude --model <model>`
- Refine migration planning: `continuous-refactoring migration refine <slug-or-path>
  (--message <text>|--file <path>) --with codex|claude --model <model>
  [--show-agent-logs]`

No lint, no typecheck, no formatter, no pre-commit. GitHub Actions `Test`
runs `uv run pytest`. **Pytest is the only code gate.** GitHub Actions
`PR Title` gates pull request title policy.

## 4. Layout

- `src/continuous_refactoring/` — flat module layout, no subpackages
- `tests/` — flat, `test_<module>.py` per source module plus behavior bundles (`test_e2e.py`, `test_run.py`, `test_run_once.py`)
- `<live-migrations-dir>/` — configurable live multi-phase plans (dog-food output); a checkout may not have `migrations/`
- `.scratchpad/` — ephemeral agent state, gitignored
- Durable user state: `~/.local/share/continuous-refactoring/…` (XDG)

## 5. Project vocabulary

- **Target** — the refactoring unit the driver is working on this iteration: a JSONL target, one matched tracked file, literal path set, random tracked-file bundle, or fallback scoped prompt.
- **Taste** — project or global prose that shapes every prompt. Project taste is XDG by default, or a repo-relative path stored as `repo_taste_path` after `init --in-repo-taste [PATH]`.
- **Scope expansion** — deciding the set of files edited together with the target (`scope_expansion.py`).
- **Classifier / routing** — chooses a target route: `cohesive-cleanup` vs `needs-plan` (`routing.py`).
- **Migration** — a multi-phase plan living under `<live-migrations-dir>/<slug>/`.
- **Visible migration directory** — direct child migration dir that is not hidden, dotted, symlinked, or internal/transactional; enumerate through `iter_visible_migration_dirs()`.
- **Consistency finding** — structured migration integrity result with shared `info | warning | error` severity and `planning-snapshot | ready-publish | execution-gate | doctor` mode.
- **Planning state** — durable resume/audit cursor at `<migration>/.planning/state.json`; it records accepted planning steps and their repo-relative stage outputs.
- **Planning stage output** — accepted planning stdout stored under `<migration>/.planning/stages/<step>.stdout.md`; repeated accepted steps use suffixed refs such as `<step>-2.stdout.md`. Failed current-step output stays in run artifacts only.
- **Planning feedback** — explicit user refinement feedback recorded in `.planning/state.json`; it reuses the `revise` planning step and is published only through staged planning/refine transactions.
- **Planning workspace** — off-live candidate migration snapshot built under project state, then copied to a live-dir transaction before publish.
- **Phase** — one step of a migration; state transitions in `phases.py`.
- **Precondition** — what must already be true before a phase may execute; stored on each manifest phase as `precondition`.
- **Definition of Done** — what must be true for a phase to count as completed; written in each phase markdown doc under `## Definition of Done`.
- **Phase cursor** — `manifest.current_phase` stores the active phase `name`; human-facing references use the relative phase file path; phase names must be unique within a migration.
- **Wake-up rule** — schedule for when the driver reconsiders an idle target.
- **Eligibility cooldown** — `manifest.cooldown_until` gates re-checks after a migration was deferred or blocked; `last_touch` records activity only.
- **Settle protocol** — `<file>.done` + sha256 handshake confirming an interactive agent is finished.
- **Status block** — the agent-emitted final-message block parsed by `decisions.py`.
- **Call role** — prompt slot recorded in artifacts, including `classify`, `refactor`, dotted planning roles such as `planning.<step>`, `planning.state`, `planning.publish`, and phase roles such as `phase.ready-check` or `phase.execute`.
- **Effort budget** — shared nominal tiers `low < medium < high < xhigh`; `--default-effort` is the normal call effort, `--max-allowed-effort` caps target overrides and phase escalation.
- **Failure snapshot** — per-attempt failure record at `…/projects/<uuid>/failures/<run_id>-attempt-NNN-retry-NN-<role>.md`. One file per failed attempt; sort to find the latest.

## 6. Code conventions

- `from __future__ import annotations` at the top of every src file, after an optional module docstring.
- Frozen dataclasses for value types; `Literal[…]` for state machines.
- Explicit `__all__` per module.
- Full-path imports (`from continuous_refactoring.X import Y`). **Never relative.**
- Boundary error type: `ContinuousRefactorError(RuntimeError)`.
- Subprocess: `subprocess.run(..., check=False, capture_output=True)`; branch on the returned `CompletedProcess`.
- Atomic writes: write to a temp file, then `os.replace`.
- Comments only when load-bearing. Clean abstractions beat prose.
- **Zero runtime dependencies** — stdlib only.

## 7. Package uniqueness rule

`src/continuous_refactoring/__init__.py` walks every public submodule's `__all__` and asserts no duplicate symbols. A collision breaks package import at boot. Any rename or addition to the package-root surface needs a project-wide check before commit. Internal modules such as `migration_manifest_codec.py`, `review_cli.py`, and `effort.py` stay out of the package-root exports.

## 8. Testing idioms

- `pytest>=8.0` only. No coverage, no hypothesis, no custom pytest markers; `pytest.mark.parametrize` is normal.
- Monkeypatching is idiomatic — not a smell.
- `tests/conftest.py` provides:
  - `write_fake_codex` — drops a Python stub for `codex` on PATH. Controlled by `FAKE_CODEX_STDOUT`, `FAKE_CODEX_STDERR`, `FAKE_CODEX_LAST_MESSAGE`, `FAKE_CODEX_TOUCH_FILE`, `FAKE_CODEX_TOUCH_CONTENT`, `FAKE_CODEX_EXIT_CODE`.
  - `_prepare_run_env` — `git init -b main` in `tmp_path`; redirects `TMPDIR` and `XDG_DATA_HOME` to the sandbox.
  - `make_run_once_args` / `make_run_loop_args` — build argparse `Namespace`s so tests bypass the CLI layer.
- Claude stream-json parsing is covered with recorded NDJSON at `tests/fixtures/claude_stream_json/selection.stdout.log`.

## 9. Structural `loop.py` work

No dedicated `loop.py` migration is active. Keep broad structural `loop.py`
edits behind a live migration plan; narrow edits are allowed only when an
active phase explicitly names `loop.py` in scope.

## 10. Load-bearing subtleties — do not "simplify" without reading

- **Settle protocol** (`agent.py:253-290`, `:413-475`) — interactive agents must write `<file>.done` containing `sha256:<hex>` matching the content's digest. Driver force-stops once digests match for `settle_window_seconds`.
- **Codex terminal reset** (`agent.py:342-372`) — raw ANSI reset after force-stop. Codex leaves the tty corrupt. Do not remove.
- **Claude stream-json unwrap** (`agent.py:68-102`) — NDJSON; prefer the last `result` event, else join assistant text blocks, else return raw.
- **Watchdog** (`agent.py:549-665`) — silent ≥5 min → SIGTERM → SIGKILL → `ContinuousRefactorError`.
- **Driver owns commits** (`refactor_attempts.py:_finalize_commit()`, called from `loop.py`) — if an agent commits mid-attempt, driver does `git reset --soft head_before` and re-commits with its own message.
- **Migration scheduling split** (`migrations.py`, `loop.py`, `phases.py`) — `last_touch` is activity bookkeeping, not the 6-hour retry gate. Deferred/blocked migrations set `cooldown_until`; successful phase completion clears deferral markers so the next ready phase can run immediately.
- **Migration tick deferral writes** (`migration_tick.py`) — ready-check deferrals are queued while scanning candidates and saved only when the tick finds no executable phase or blocks for human review. Do not save a deferred manifest before checking later candidates; that dirties the worktree and can make ready-checks reject runnable phases.
- **Migration visibility + consistency gate** (`migration_consistency.py`, `migration_tick.py`, `loop.py`, `review_cli.py`) — candidate scans use `iter_visible_migration_dirs()` so hidden/dotted/internal/symlink dirs are invisible to tick/list/review commands. Before ready-check, `execution-gate` consistency errors block phase execution; `info`/`warning` never block.
- **Manifest codec boundary** (`migration_manifest_codec.py`, `migrations.py`) — codec owns legacy `ready_when`, legacy integer `current_phase`, duplicate phase-name rejection, and saved JSON formatting. `load_manifest()` / `save_manifest()` own filesystem and JSON boundary errors.
- **Planning state codec boundary** (`planning_state.py`, `planning.py`) — `.planning/state.json` is valid only when completed steps replay through the branching planning graph to `next_step`; recorded outputs must be repo-relative files inside the migration directory. User refinement feedback is durable state, and append-only `revision_base_step_counts` anchors let refinement reuse `revise` from review cursors or unexecuted ready terminal decisions; legacy `revision_base_step_count` decodes as one anchor. Persist accepted step stdout after the step is validated; do not add durable fields for failed current-step output.
- **Planning publish transaction** (`planning_publish.py`) — publish copies the complete workspace snapshot to `__transactions__/<token>/staged`, validates it, checks same-device and `base_snapshot_id`, moves live to `rollback`, moves staged live, validates live, then deletes rollback. On post-rollback failure, move bad live to `failed` before restoring rollback. Transaction directories are invisible to scheduling/list candidates but visible to `migration doctor --all`. Do not bypass the lock or dirty-live check.
- **One-step planning engine** (`planning.py`) — product planning entry points call `run_next_planning_step()` so one action runs exactly `PlanningState.next_step`, records accepted stdout/state in an off-live workspace, and publishes through `planning_publish.py`. Failed current-step output is never durable resume input. `run_planning` is intentionally not package-exported.
- **Planning resume scheduling** (`migration_tick.py`, `loop.py`, `routing_pipeline.py`) — normal automation runs one eligible `status: planning` step before ready/in-progress phase ticks and before source-target routing. Missing or invalid `.planning/state.json` blocks automation with planning failure evidence; `status: planning` must never enter phase ready-check or phase execution.
- **Focused planning reselection** (`loop.py`, `migration_tick.py`) — focused mode tracks planning migrations abandoned with `new-target` only in memory for the current run, skips them while another planning or phase candidate is eligible, and retries them only when no alternative remains. Do not persist this as `cooldown_until`; planning step failure is not a durable readiness deferral.
- **Review CLI boundary** (`cli.py`, `review_cli.py`) — `cli.py` owns parser wiring; staged migration review internals live in `review_cli.py`, publish only through `planning_publish.py`, and stay internal/out of package-root `_SUBMODULES`. Review mutation is only exposed through `migration review`.
- **Migration CLI boundary** (`cli.py`, `migration_cli.py`) — `cli.py` owns parser wiring only; `migration_cli.py` owns namespace dispatch, read-only list/doctor behavior, and the contained slug/path resolver used by mutation commands. Mutating subcommands delegate their internals to focused modules such as `review_cli.py` or the planning refine entry point. Resolver targets must stay direct visible children of the configured live migrations root and reject symlink, outside, parent-traversal, and ambiguous paths.
- **Human-review gating** (`planning.py`, `migration_tick.py`, `review_cli.py`) — migrations with `awaiting_human_review=true` must be invisible to automated migration ticks/ready-checks until canonical `migration review` clears the flag through staged publish. `migration refine` may reopen an unexecuted ready migration to planning, but it is user feedback, not review approval.
- **Migration terminology split** (`migrations.py`, `planning.py`, `prompts.py`) — manifest `precondition` gates phase start; phase markdown `## Definition of Done` governs completion.
- **Run-level baseline validation** (`loop.py`) — `run-once`, `run`, and `--focus-on-live-migrations` run the configured validation command after the clean-worktree check and before routing/refactoring. A red baseline stops as `baseline_failed`, not migration human review.
- **Phase execution validation gate** (`phases.py`, `prompts.py`, `loop.py`) — a migration phase is complete only after host-side full validation passes. `execute_phase()` retries validation-red attempts from `head_before` up to the effective `--max-attempts` budget, and the phase prompt must include the literal configured validation command plus the phase file's Definition of Done as the completion contract.
- **Effort budgeting** (`effort.py`, `loop.py`, `migration_tick.py`, `planning.py`) — `run` / `run-once` default to `--default-effort low` and `--max-allowed-effort xhigh`; there is no `--effort` alias on those commands. Target `effort-override` changes that target's default but is still capped. Migration `required_effort` above the cap defers the phase without failing the run. Manual `migration review` and `migration refine` operations use fixed internal `high` effort. Taste agent actions do not accept `--effort`; they always use fixed `medium` effort.
- **Taste injection** — every prompt includes a `## Taste` section. `tests/test_prompts.py` enforces this via `_TASTE_INJECTED_PROMPTS`. Do not drop it.
- **Taste read boundary** (`config.py`, `cli.py`, `loop.py`) — `load_taste()` translates unreadable project/global taste reads into `ContinuousRefactorError`; CLI stale-taste checks and loop taste loading must treat that boundary failure as non-fatal and skip/fall back instead of leaking raw `OSError`/`PermissionError`.
- **Repo-local taste routing** (`config.py`, `cli.py`) — `ProjectEntry.repo_taste_path` is stored repo-relative in the XDG manifest and resolved through `resolve_project_taste_path()`. Keep `init`, `taste`, stale warnings, and run prompt loading on that helper so the active taste path does not drift.
- **Init reconfiguration moves state** (`cli.py`) — re-running `init` with `--in-repo-taste` or `--live-migrations-dir` moves existing taste/live migration state before updating manifest pointers; destination conflicts require `--force`.

## 11. Surprising CLI semantics

- Targeting is **first-match-wins** across `--targets > --globs > --extensions > --paths`. Multiple flags silently use the highest.
- `run` requires targeting or `--scope-instruction`, and also requires `--max-refactors` unless `--targets` or `--focus-on-live-migrations` is set.
- `--max-attempts 0` means **unlimited**, not zero. A WARN fires at startup.
- `run-once` and `run` both create local commits only; the driver never publishes branch updates.

## 12. XDG + artifacts

- Durable: `~/.local/share/continuous-refactoring/manifest.json`, `projects/<uuid>/taste.md` unless repo-local taste is configured, `…/failures/<snapshot>.md`, `global/taste.md`.
- Per-run (ephemeral): `$TMPDIR/continuous-refactoring/<run-id>/summary.json`, `events.jsonl`, `run.log`.

## 13. Branches, PRs, and releases

- All work happens off `main`.
- Changes land by PR. Do not push directly to `main`.
- PR titles must match:
  `<type>(optional-scope)!: Capitalized Title Text`, where type is
  `feat|chore|fix|refactor|migration` and scope/`!` are optional.
- Prefixes and scopes are lowercase. Title text starts capitalized.
- Release Please owns version bumps, `CHANGELOG.md`, tags, and GitHub releases.
- Release-driving commits follow Conventional Commits: `feat:` is minor,
  `fix:` is patch, and breaking changes require `!` or a `BREAKING CHANGE:`
  footer.
- Non-release cleanup uses `chore:` or `refactor:` unless it truly changes user
  behavior.
- Commit subject prefix: `continuous refactor: <path>` (dominant pattern).
- Driver-generated commit bodies include a concise `Why:` section and validation
  context when available.

## 14. What NOT to do

- No re-export shims on refactor.
- No new runtime dependencies.
- No relative imports.
- Do not drop `## Taste` from prompts.
- Do not simplify the ANSI terminal reset in `agent.py`.
- Do not structurally refactor `loop.py` without an active migration plan.
- Do not amend commits in the driver path (driver uses `git reset --soft`).
- Driver never creates, switches, or deletes branches. The user controls branching.
- Do not hand-edit release versions except for Release Please bootstrap or
  emergency repair.

## 15. Read-first pointers

- `README.md` — feature tour and CLI reference.
- `<live-migrations-dir>/<live>/plan.md` — active structural work, when this checkout has a live migrations dir.
- `src/continuous_refactoring/__init__.py` — public surface and uniqueness check.
- `tests/conftest.py` — test env patterns and fake agents.
- `src/continuous_refactoring/prompts.py` — prompt templates and taste injection.
