# AGENTS.md

## 1. Identity

Test-gated refactor loop that drives `codex` and `claude` CLIs through small, validated commits. Zero runtime deps, stdlib only. Dog-foods itself — the driver's biggest active target is its own `loop.py`. User-facing docs live in `README.md`; this file is the mutator's contract.

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
- Entry: `continuous-refactoring --help` (or `python -m continuous_refactoring`)

No lint, no typecheck, no formatter, no CI, no pre-commit. **Pytest is the only gate.**

## 4. Layout

- `src/continuous_refactoring/` — flat, ~13 modules, no subpackages
- `tests/` — flat, `test_<module>.py` per source module plus behavior bundles (`test_e2e.py`, `test_run.py`, `test_run_once.py`)
- `migrations/` — live multi-phase plans (dog-food output)
- `.scratchpad/` — ephemeral agent state, gitignored
- Durable user state: `~/.local/share/continuous-refactoring/…` (XDG)

## 5. Project vocabulary

- **Target** — a source path the driver is working on this iteration.
- **Taste** — project or global prose that shapes every prompt (see XDG paths below).
- **Scope expansion** — deciding the set of files edited together with the target (`scope_expansion.py`).
- **Classifier / routing** — picks which agent handles a target (`routing.py`).
- **Migration** — a multi-phase plan living under `migrations/<slug>/`.
- **Phase** — one step of a migration; state transitions in `phases.py`.
- **Precondition** — what must already be true before a phase may execute; stored on each manifest phase as `precondition`.
- **Definition of Done** — what must be true for a phase to count as completed; written in each phase markdown doc under `## Definition of Done`.
- **Phase cursor** — `manifest.current_phase` stores the active phase `name`; human-facing references use the relative phase file path; phase names must be unique within a migration.
- **Wake-up rule** — schedule for when the driver reconsiders an idle target.
- **Eligibility cooldown** — `manifest.cooldown_until` gates re-checks after a migration was deferred or blocked; `last_touch` records activity only.
- **Settle protocol** — `<file>.done` + sha256 handshake confirming an interactive agent is finished.
- **Status block** — the driver's end-of-attempt summary written to artifacts.
- **Call role** — `classifier | planner | editor | reviewer` slot filled in a prompt.
- **Failure snapshot** — per-attempt failure record at `…/projects/<uuid>/failures/<run_id>-attempt-NNN-retry-NN-<role>.md`. One file per failed attempt; sort to find the latest.

## 6. Code conventions

- `from __future__ import annotations` at the top of every src file.
- Frozen dataclasses for value types; `Literal[…]` for state machines.
- Explicit `__all__` per module.
- Full-path imports (`from continuous_refactoring.X import Y`). **Never relative.**
- Boundary error type: `ContinuousRefactorError(RuntimeError)`.
- Subprocess: `subprocess.run(..., check=False, capture_output=True)`; branch on the returned `CompletedProcess`.
- Atomic writes: write to a temp file, then `os.replace`.
- Comments only when load-bearing. Clean abstractions beat prose.
- **Zero runtime dependencies** — stdlib only.

## 7. Package uniqueness rule

`src/continuous_refactoring/__init__.py` walks every submodule's `__all__` and asserts no duplicate symbols. A collision breaks package import at boot. Any rename or addition needs a project-wide check before commit.

## 8. Testing idioms

- `pytest>=8.0` only. No coverage, no hypothesis, no markers.
- Monkeypatching is idiomatic — not a smell.
- `tests/conftest.py` provides:
  - `write_fake_codex` — drops a Python stub for `codex` on PATH. Controlled by `FAKE_CODEX_STDOUT`, `FAKE_CODEX_LAST_MESSAGE`, `FAKE_CODEX_TOUCH_FILE`, `FAKE_CODEX_EXIT_CODE`.
  - `_prepare_run_env` — `git init -b main` in `tmp_path`; redirects `TMPDIR` and `XDG_DATA_HOME` to the sandbox.
  - `make_run_once_args` / `make_run_loop_args` — build argparse `Namespace`s so tests bypass the CLI layer.
- Claude stream-json parsing is covered with recorded NDJSON at `tests/fixtures/claude_stream_json/selection.stdout.log`.

## 9. Active migration of `loop.py`

- Path: `migrations/src-continuous-refactoring-loop-py-20260417T124216/`
- Plan: phase 1 (`decisions.py`) is landed; the remaining live phases extract `failure_report.py` and `routing_pipeline.py`, then do a no-new-extraction tidy pass in `loop.py`.
- Realistic size target for this live four-phase migration: `loop.py` roughly 950–1100 lines after phases 2–4. Reaching ~500 needs a later follow-up extraction migration; do not assume phase 3 or 4 can get there alone.
- **Before editing `loop.py`, read `plan.md` and the current phase doc.** Structural edits may collide with in-flight phases.
- **No re-export shims.** Symbol moves update every call site and every test monkeypatch target in the same commit.
- When a migration completes, remove it from this section.

## 10. Load-bearing subtleties — do not "simplify" without reading

- **Settle protocol** (`agent.py:253-290`, `:413-475`) — interactive agents must write `<file>.done` containing `sha256:<hex>` matching the content's digest. Driver force-stops once digests match for `settle_window_seconds`.
- **Codex terminal reset** (`agent.py:342-372`) — raw ANSI reset after force-stop. Codex leaves the tty corrupt. Do not remove.
- **Claude stream-json unwrap** (`agent.py:68-102`) — NDJSON; prefer the last `result` event, else join assistant text blocks, else return raw.
- **Watchdog** (`agent.py:549-665`) — silent ≥5 min → SIGTERM → SIGKILL → `ContinuousRefactorError`.
- **Driver owns commits** (`loop.py:1265-1269`) — if an agent commits mid-attempt, driver does `git reset --soft head_before` and re-commits with its own message.
- **Migration scheduling split** (`migrations.py`, `loop.py`, `phases.py`) — `last_touch` is activity bookkeeping, not the 6-hour retry gate. Deferred/blocked migrations set `cooldown_until`; successful phase completion clears deferral markers so the next ready phase can run immediately.
- **Migration terminology split** (`migrations.py`, `planning.py`, `prompts.py`) — manifest `precondition` gates phase start; phase markdown `## Definition of Done` governs completion. Legacy manifest `ready_when` is read-only compatibility.
- **Phase execution validation gate** (`phases.py`, `prompts.py`, `loop.py`) — a migration phase is complete only after host-side full validation passes. `execute_phase()` retries validation-red attempts from `head_before` up to the effective `--max-attempts` budget, and the phase prompt must include the literal configured validation command plus the phase file's Definition of Done as the completion contract.
- **Taste injection** — every prompt includes a `## Taste` section. `tests/test_prompts.py` enforces this via `_TASTE_INJECTED_PROMPTS`. Do not drop it.

## 11. Surprising CLI semantics

- Targeting is **first-match-wins** across `--targets > --globs > --extensions > --paths`. Multiple flags silently use the highest.
- `--max-attempts 0` means **unlimited**, not zero. A WARN fires at startup.
- `run-once` and `run` both create local commits only; the driver never publishes branch updates.

## 12. XDG + artifacts

- Durable: `~/.local/share/continuous-refactoring/manifest.json`, `projects/<uuid>/taste.md`, `…/failures/<snapshot>.md`, `global/taste.md`.
- Per-run (ephemeral): `$TMPDIR/continuous-refactoring/<run-id>/summary.json`, `events.jsonl`, `run.log`.

## 13. Commit conventions

- Commit prefix: `continuous refactor: <path>` (dominant pattern).

## 14. What NOT to do

- No re-export shims on refactor.
- No new runtime dependencies.
- No relative imports.
- Do not drop `## Taste` from prompts.
- Do not simplify the ANSI terminal reset in `agent.py`.
- Do not refactor `loop.py` without reading the live migration plan.
- Do not amend commits in the driver path (driver uses `git reset --soft`).
- Driver never creates, switches, or deletes branches. The user controls branching.

## 15. Read-first pointers

- `README.md` — feature tour and CLI reference.
- `migrations/<live>/plan.md` — active structural work.
- `src/continuous_refactoring/__init__.py` — public surface and uniqueness check.
- `tests/conftest.py` — test env patterns and fake agents.
- `src/continuous_refactoring/prompts.py` — prompt templates and taste injection.
