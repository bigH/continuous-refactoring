# continuous-refactoring

Small, test-gated cleanup commits by an AI coding agent.

Think of it as a supervised janitor loop: the agent proposes a cleanup, your tests decide if it stays.

## Fastest way to get one refactor

Once installed:

```bash
continuous-refactoring init
continuous-refactoring run-once \
  --with codex --model gpt-5 --effort high \
  --extensions .py
```

That gives you one pass on the current branch. If validation passes, it leaves you with a local commit to inspect.

## Got tokens to burn?

```bash
continuous-refactoring run \
  --with codex --model gpt-5 --effort high \
  --extensions .py \
  --max-refactors 10 \
  --max-attempts 2
```

That keeps sweeping targets until it runs out, hits your caps, or starts failing.

## What it does

- Resolves a target from `--targets`, `--globs`, `--extensions`, or `--paths`, with optional natural-language scoping via `--scope-instruction`.
- Runs the agent with a refactoring prompt + your "taste" guidelines.
- Runs your validation command (default: `uv run pytest`).
- In `run`, if green and there's a diff, commits and pushes. In `run-once`, it commits locally and leaves the branch for you to inspect.
- Repeats until it runs out of targets, hits the retry budget, or stacks too many failures.

## Requirements

- Python 3.10+
- [uv](https://github.com/astral-sh/uv)
- `codex` or `claude` CLI on your `PATH` (whichever backend you pick)
- A git repo with a clean worktree

## Install

```bash
uv sync
uv pip install -e .
```

That gives you the `continuous-refactoring` command.

## Quickstart

```bash
# 1. Register the repo (creates a project dir under ~/.local/share/continuous-refactoring)
continuous-refactoring init

# 2. (Optional) Write your refactoring taste — either edit the file, have an agent interview you,
#    or refine an existing draft collaboratively
continuous-refactoring taste --interview --with codex --model gpt-5 --effort high
continuous-refactoring taste --refine --with codex --model gpt-5 --effort high

# 3. Do one pass
continuous-refactoring run-once \
  --with codex --model gpt-5 --effort high \
  --extensions .py

# 4. Or run the loop over a batch of targets
continuous-refactoring run \
  --with claude --model claude-opus-4-6 --effort high \
  --globs 'src/**/*.py' \
  --max-refactors 10 \
  --max-attempts 2 \
  --sleep 5
```

## Subcommands

| Command | What it does |
|---|---|
| `init` | Registers this directory as a project, creates a default `taste.md`, and can store `--live-migrations-dir`. |
| `taste` | Prints the active taste file path. Add `--interview` to have an agent author it, `--refine` to iteratively improve an existing taste doc, `--upgrade` to refresh stale taste dimensions, `--global` for the shared file, and `--force` to let `--interview` overwrite custom content after writing a `.bak`. |
| `run-once` | Single pass on one resolved target. No retry, no push. If there is a diff and validation passes, it commits locally and prints the diffstat. |
| `run` | The loop. Iterates targets, retries on failure, commits successful targets, and pushes unless `--no-push` is set. |
| `upgrade` | Checks that the global config manifest is current, rewrites it idempotently, and warns if the global taste file is stale. |
| `review list` | Lists migrations flagged for human review (`awaiting_human_review`). |
| `review perform <migration>` | Starts an interactive agent session to resolve a flagged migration's review. Requires `--with`, `--model`, and `--effort`. |

## Targeting / Useful flags

### Target selection

Target resolution is first-match-wins:
`--targets` > `--globs` > `--extensions` > `--paths`

These flags are not mutually exclusive, but only the highest-priority populated source is used.

- `--targets path/to/targets.jsonl` — explicit list; one JSON object per line with `description`, `files`, optional `scoping`, `model-override`, `effort-override`.
- `--globs 'src/**/*.py:tests/**/*.py'` — colon-separated globs; each matched file becomes its own target.
- `--extensions .py,.ts` — shorthand that expands to `**/*.py`, `**/*.ts`; each matched file becomes its own target.
- `--paths a.py:b.py` — literal paths, all treated as one target.
- `--scope-instruction "clean up the auth module"` — extra free-text scoping. If file-based targeting resolves nothing, this becomes the useful fallback context.

If you provide none of `--targets`, `--globs`, `--extensions`, or `--paths`, then `run` and `run-once` require `--scope-instruction`.

### Migrations & taste flags

- `init --live-migrations-dir PATH` — enables the larger-refactoring workflow for this project. The path is stored repo-relative in the project registry and created if missing.
- `taste --refine` — opens a collaborative editing session for the taste file. The agent keeps refining until you tell it to write, then the session ends automatically after the settled write.
- `taste --upgrade` — re-interviews for taste dimensions added since your last version. No-op when already current; use `taste --refine` if you want to rework the doc anyway.
- `taste --force` — only applies to `--interview`; it allows a customized taste file to be overwritten after backing it up to `taste.md.bak`.

### Shared `run` / `run-once` flags

- `--with`, `--model`, `--effort` — required agent backend/model/effort selection.
- `--repo-root PATH` — repository root; defaults to the current directory.
- `--validation-command` — defaults to `uv run pytest`. Swap it for whatever keeps your repo honest.
- `--timeout` — per-agent-call timeout in seconds.
- `--show-agent-logs` / `--show-command-logs` — mirror output to your terminal instead of just logging.
- `--refactoring-prompt` — override the default refactoring prompt.
- `--fix-prompt` — override the retry amendment prompt. Useful for `run`; accepted by `run-once` for flag symmetry.

### `run`-only flags

- `--max-attempts N` — per-target retry budget. `1` = no retry, `0` = unlimited (which means permanently broken targets will never give up).
- `--max-refactors N` — cap the number of targets per run. Required unless you use `--targets`.
- `--max-consecutive-failures N` — bail after N targets fail in a row. Default 3.
- `--sleep SECONDS` — pause between completed targets. Useful when you want a long batch without hammering the repo or your agent budget.
- `--no-push` — keep commits local.
- `--push-remote NAME` — remote used when pushing. Default `origin`.
- `--commit-message-prefix TEXT` — prefix for successful refactor or migration-plan commits. Default `continuous refactor`.

## Safety behaviors

- Refuses to start with a dirty worktree.
- Runs on the current branch. Commits land there. Push target is also the current branch (unless `--no-push`).
- `run` baselines your validation command before touching anything. If the baseline is already red, it stops.
- On a failed attempt, resets back to the pre-attempt HEAD and cleans workspace changes before retrying or moving on.
- Watchdog kills any agent or test process that's been silent for 5 minutes.

## Where the artifacts live

Each run writes to `$TMPDIR/continuous-refactoring/<run-id>/`:

- `summary.json` — rolling status, counts, per-attempt stats
- `events.jsonl` — structured event log
- `run.log` — human-readable log
- `attempt-NNN/[retry-NN/]refactor/` — per-attempt agent + test stdout/stderr

The path prints at startup. Grep it when something goes sideways.

## Taste files

The taste file is a short bullet list of your refactoring preferences. It gets injected into every agent prompt.

- Project taste: `~/.local/share/continuous-refactoring/projects/<uuid>/taste.md`
- Global taste: `~/.local/share/continuous-refactoring/global/taste.md`

Project taste wins over global. Use `taste --interview` to bootstrap one, `taste --refine` to rework it with an agent, or edit the file directly any time.

## Larger refactorings

When a cleanup is too big for a single commit — needs a plan, touches many files, or should ship in stages — use the migrations model.

### Enabling it

```bash
continuous-refactoring init --live-migrations-dir migrations/
```

This tells the CLI where to store migration artifacts. The path is repo-relative, stored in the XDG project registry (no project config file is created). When this directory is unset, the one-shot cleanup path remains byte-identical to the default behavior.

### How it works

Each `run` / `run-once` tick now checks for eligible migration work before falling back to single-commit cleanups:

1. **Classify** — a classifier agent reads the target and decides: `cohesive-cleanup` (one-shot path) or `needs-plan` (migration path).
2. **Plan** — for `needs-plan` targets, a six-stage planning workflow runs: generate approaches → pick best → expand into phases → review → revise → final review. Artifacts land under `<live-migrations-dir>/<migration-name>/`.
3. **Execute** — each phase is a self-contained unit of work. The tick picks the oldest eligible migration, checks whether its current phase is ready, and executes it on the current branch; commit message identifies the migration as `migration/<name>/phase-N/<phase.name>`.

### Migration directory layout

```
<live-migrations-dir>/
  <migration-name>/
    manifest.json          # status, phases, wake-up schedule
    plan.md                # the expanded plan
    approaches/            # candidate approaches considered during planning
    phase-1-<name>.md      # per-phase specification
    phase-2-<name>.md
    ...
  __intentional_skips__/   # migrations rejected at final review
```

### Wake-up rules

Migrations don't run on every tick. A migration is eligible when **all** of:

- At least **6 hours** since its last touch (safety invariant — always enforced, cannot be overridden).
- Either `wake_up_on` has elapsed, **or** it has been stale for ≥7 days with no `wake_up_on` set.

This prevents the loop from hammering a stuck migration while still ensuring nothing is forgotten.

### Phase model

Each migration moves through phases sequentially. Before executing a phase, a ready-check agent verifies that prerequisites are met. Possible outcomes:

- **ready: yes** — phase executes; on green tests, the phase is marked done and the migration advances.
- **ready: no** — manifest is bumped with a future `wake_up_on`; the tick moves on.
- **ready: unverifiable** — the migration is flagged `awaiting_human_review`. Use `review list` to find it and `review perform <migration> --with ... --model ... --effort ...` to resolve it interactively.

### What the CLI doesn't do

Rollout mechanics — feature flag names, deploy tooling, metric dashboards, canary analysis — are the coding agent's responsibility, not a CLI-visible concern. The CLI manages the planning and phased execution workflow; the agent writes whatever rollout code the plan calls for.
