# Prompt: design plan + orchestrator for "larger refactorings" support

You are the architect for a significant extension of `continuous-refactoring`. Your job is to produce two artifacts that together let us implement this feature end-to-end. **Do not write implementation code beyond the orchestrator itself.** Do not modify `src/`.

## Mission

`continuous-refactoring` today runs an agent loop that performs single-session cleanup refactorings (dead code, wrapper removal, test hardening) gated by a validation command. We are extending it to handle two new task classes:

1. **Multi-agent complex tasks** — refactorings too big for one agent session, requiring a planning phase that produces a multi-phase plan.
2. **Phased-rollout tasks** — changes that must ship incrementally with signal-gated progression between phases.

The existing one-shot path must remain fully functional and unchanged in behavior when no live migrations are active and the classifier routes to it.

## Outputs (exactly two)

### 1. `docs/plans/larger-refactorings.md`

A plan file with this structure:

- **Header:** `Status: todo` (work ready) | `Status: awaiting <human|other-plan-slug|clarification>` (blocked) | `Status: failed — <short reason>` (set by orchestrator on error).
- **Problem statement** — ≤10 lines.
- **Mermaid diagram** showing new components and their relationships to existing ones (`cli.py`, `loop.py`, `agent.py`, `prompts.py`, `targeting.py`, `artifacts.py`).
- **Task list.** Each task has:
  - `id` — stable (e.g. `T3.2`)
  - `title`
  - `type` — `code` | `config` | `docs` | `test`
  - `touches` — paths/globs
  - `blocked_by` — task ids
  - `review_criteria` — concrete conditions the review agent can verify
  - `done` — starts `false`

Pick a single serialization (YAML-fronted markdown blocks, or a structured `## Tasks` section — your call), document it in the file, and make sure the orchestrator can parse it. Group tasks into PR-sized batches; each batch must leave the repo shippable.

### 2. `scripts/run_larger_refactorings_plan.py`

A Python orchestrator that:

- Reads `docs/plans/larger-refactorings.md`.
- If `Status: failed` → print reason, exit 1.
- If `Status: awaiting …` → print what it's waiting on, exit 0.
- Else: find the next task with `done: false` and all `blocked_by` satisfied.
  - Dispatch an agent (reuse helpers from `src/continuous_refactoring/agent.py`) with a task-specific prompt built from the task's `title`, `touches`, and `review_criteria`.
  - When the step completes, run a **review pass**: a second agent invocation whose job is to ensure the plan keeps moving. It verifies `review_criteria` and fixes small issues itself (not a full code review). It runs the project's tests.
  - On success: flip `done: true`, commit plan update + code changes as one commit, loop to next task.
  - On failure (agent errors, validation red, review cannot recover within a bounded attempt budget): set `Status: failed — <reason>`, commit the plan-only update, exit 1.
- Resumable: re-running picks up at the next undone, unblocked task. No additional state file — the plan is the source of truth.
- Operates on the current branch; never pushes.

## Design decisions (locked — bake these into the plan)

### Live-migrations directory (in-repo)

- User specifies path via `continuous-refactoring init --live-migrations-dir <path>`. Stored in the XDG per-project registry alongside existing state. **No project config file.**
- Layout:
  - `<dir>/<migration-name>/manifest.json`
  - `<dir>/<migration-name>/plan.md`
  - `<dir>/<migration-name>/approaches/<idea>.md`
  - `<dir>/<migration-name>/phase-<n>-<name>.md`
  - `<dir>/__intentional_skips__/<name>.md`

### Manifest (`manifest.json`) — at minimum

`name`, `created_at`, `last_touch`, `wake_up_on` (nullable), `awaiting_human_review` (bool), `status` (`planning` | `ready` | `in-progress` | `skipped` | `done`), `current_phase` (int), `phases` (ordered `{name, file, done, ready_when}`). All timestamps UTC ISO8601.

### Wake-up mechanics

On every `run`, for each migration, eligibility =
`(now − last_touch) ≥ 6h` **AND** (`wake_up_on ≤ now` **OR** `(now − last_touch) ≥ 7d`).

If eligible, dispatch the ready-check agent for the current phase. If ready → work the phase. Otherwise → update `wake_up_on`, bump `last_touch`, move on. **Never bypass the 6h cooldown** regardless of what agents write (safety invariant).

### `ready_when`

- Plaintext expectation inside each phase file (e.g. "p95 /orders latency < 400ms for 48h").
- Evaluated by the **coding agent**, which is expected to have the required skills/MCPs configured to access the signals. No project-config declaration of signal sources — agent capability owns this.
- If the agent cannot verify the signal, the refactor is parked: record in `__intentional_skips__/<name>.md` during planning, or leave the migration stuck with `awaiting_human_review` if discovered mid-flight.

### Run flow (updated `run` / `run-once`)

Each tick performs exactly one unit of work:

1. Scan migrations. Work one phase of the highest-priority eligible+ready migration, if any.
2. Otherwise, pick a target as today.
3. **Classifier agent** routes: cohesive-cleanup vs needs-plan. Inputs: target description, touched files, recent artifacts. If it misjudges, existing `max_consecutive_failures` catches it — no re-routing mid-target.
4. Cohesive-cleanup → existing one-shot path (unchanged).
5. Needs-plan → run planning phase. Planning is the unit; no source changes land beyond plan artifacts.

`run` loops one unit at a time with no batching. Throughput comes from cadence, not per-tick size.

### Planning phase

1. **Approaches** — one agent writes N distinct candidates at `approaches/<idea>.md`.
2. **Pick-best** — one agent annotates each `approaches/*.md` with accepted/rejected + reasoning, then stubs `plan.md` with the chosen approach.
3. **Expand** — one agent expands the chosen approach into full `plan.md` with phases.
4. **Review + fix × 2** — two rounds of review-and-revise.
5. **Final review** — one agent outputs exactly one of `{approve-auto, approve-needs-human, reject}`:
   - `approve-auto` → `status: ready`.
   - `approve-needs-human` → `awaiting_human_review: true`, `status: ready`.
   - `reject` → write `__intentional_skips__/<name>.md` with target, intended outcome, blocker reason; migration abandoned.
6. Commit all planning artifacts + manifest. This counts as one `run-once` unit.

### Execution phase

- A phase = a shippable increment.
- Phase ↔ 1..N agent runs; prefer 1:1, use 1:n only when the increment exceeds a session.
- Each phase lands on its own branch. The branch is complete when the increment ships.

### CLI additions

- `continuous-refactoring review list` — show migrations with `awaiting_human_review = true`.
- `continuous-refactoring review perform <migration>` — spawn an agent that asks the human the questions needed to unblock, captures answers into the manifest/plan, clears the flag.
- `continuous-refactoring upgrade` — upgrades global config only. Errors if config version missing/stale. Warns (does not block) if tastes need upgrading.
- `continuous-refactoring taste --upgrade` — incremental taste upgrade (asks only about new dimensions since the stored version).
- Every command warns if tastes need upgrading.

### Taste changes

- Taste docs now carry a `taste-scoping-version` header.
- This version bump **invalidates existing tastes** — user must run `taste --upgrade` (forced this time; later bumps can defer).
- Tastes gain two dimensions: large-scope decision preferences (when to split/unify/introduce interfaces) and rollout *style* (caution level, preferred patterns — e.g. "always feature-flag user-visible changes"). Rollout **mechanism** (what flags/deploys exist, how to reach metrics) is not taste — it lives in the coding agent's skills/MCPs.

### Relationship summary

No project config file exists. Per-user taste lives in XDG. Per-project wiring (signals, deploy tools) is the coding agent's capability, not ours to declare. In-repo content is limited to the live-migrations directory.

## Constraints

- The existing one-shot refactoring path must remain byte-identical in behavior when classifier returns cohesive-cleanup. Add a test that asserts this.
- Match existing code style: short functions, idiomatic Python, types, minimal comments. Scan `src/continuous_refactoring/` thoroughly before writing tasks.
- Manifests use stdlib `json`. Plan/phase/approach files are plain markdown. No new runtime dependencies without an explicit task justifying them.
- Every new CLI subcommand ships with tests covering happy path + one failure mode.
- Tests hit real subprocesses/files where reasonable; mock only at the agent-invocation boundary.
- No stub implementations. No "TODO: implement later" on the critical path.

## If stuck

- Design contradiction you cannot resolve → write the plan with `Status: awaiting clarification`, add a top-level `## Open questions` section listing the blockers, stop.
- Existing code structure blocks the change without a prior refactor → write that prior refactor as a separate plan in `docs/plans/` and make `larger-refactorings.md` depend on it via `Status: awaiting <that-plan-slug>`.

## Required reading (before writing anything)

- `src/continuous_refactoring/cli.py`
- `src/continuous_refactoring/loop.py`
- `src/continuous_refactoring/agent.py`
- `src/continuous_refactoring/prompts.py`
- `src/continuous_refactoring/targeting.py`
- `src/continuous_refactoring/artifacts.py`
- `README.md`
- Anything taste-related you find under `src/`

Reference concrete `path:line` ranges in your `touches` fields.

## Verification checklist (all must hold before you set `Status: todo`)

- [ ] Every design decision above is covered by at least one task.
- [ ] Every task's `review_criteria` is specific enough for an agent to judge mechanically.
- [ ] Dependencies form a DAG (no cycles).
- [ ] The first batch of tasks leaves the repo shippable with the one-shot path intact.
- [ ] The orchestrator specification is detailed enough that the task to build the orchestrator can itself be driven by a review agent.
- [ ] A regression test exists for the one-shot path post-change.
- [ ] The Mermaid diagram matches the task list.
- [ ] The plan's task format is documented in the plan and parseable by the orchestrator you write.
