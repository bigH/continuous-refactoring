# continuous-refactoring

[![GitHub repo](https://img.shields.io/badge/github-repo-green)](https://github.com/bigH/continuous-refactoring)
[![PyPI](https://img.shields.io/pypi/v/continuous-refactoring.svg)](https://pypi.org/project/continuous-refactoring/)
[![Tests](https://github.com/bigH/continuous-refactoring/actions/workflows/test.yml/badge.svg)](https://github.com/bigH/continuous-refactoring/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/bigH/continuous-refactoring/blob/main/LICENSE)

Small, test-gated cleanup commits by an AI coding agent.

Think of it as a supervised janitor loop: the agent proposes a cleanup, your tests decide if it stays.

Here's [an article](https://artisincode.com/essays/how-i-use-unspent-tokens/) I wrote about it.

## Install

Try it without installing:

```bash
uvx continuous-refactoring --help
```

Or install it with [uv](https://docs.astral.sh/uv/guides/tools/):

```bash
uv tool install continuous-refactoring
```

Or with [pipx](https://pypa.github.io/pipx/):

```bash
pipx install continuous-refactoring
```

Or with pip:

```bash
pip install continuous-refactoring
```

For a checkout:

```bash
uv sync
uv pip install -e .
```

That gives you the `continuous-refactoring` command.

The CLI itself can be installed without `uv`, but the default validation command
is `uv run pytest`. Pass `--validation-command pytest` or a project-specific
script when the target repo does not use `uv`.

Maintainers: see the [release checklist](https://github.com/bigH/continuous-refactoring/blob/main/docs/release.md).

## Fastest way to get one refactor

Once installed:

```bash
continuous-refactoring init
continuous-refactoring run-once \
  --with codex --model gpt-5 \
  --extensions .py
```

That gives you one pass on the current branch. If validation passes, it leaves you with a local commit to inspect.

## Got tokens to burn?

```bash
continuous-refactoring run \
  --with codex --model gpt-5 --default-effort high \
  --extensions .py \
  --max-refactors 10 \
  --max-attempts 2
```

That runs up to 10 refactor actions, then stops sooner if the finite target file
runs out or the loop starts failing. Use `run --focus-on-live-migrations` when
you want the loop to work only on eligible live migrations; it bypasses target
selection and `--max-refactors`.

## What it does

- Resolves each source action from `--targets`, `--globs`, `--extensions`, or `--paths`, with optional natural-language scoping via `--scope-instruction`.
- Runs the agent with a refactoring prompt + your "taste" guidelines.
- Runs your validation command (default: `uv run pytest`).
- If green and there's a diff, it commits locally and leaves the branch for you to inspect.
- Repeats until it spends the action budget, exhausts a finite target file, hits the retry budget, or stacks too many failures.

## Requirements

- Python 3.10+
- [uv](https://github.com/astral-sh/uv)
- `codex` or `claude` CLI on your `PATH` (whichever backend you pick)
- A git repo with a clean worktree

## Quickstart

```bash
# 1. Register the repo (creates a project dir under ~/.local/share/continuous-refactoring)
continuous-refactoring init
# Or keep project taste in the repo:
continuous-refactoring init --in-repo-taste

# 2. (Optional) Write your refactoring taste — either edit the file, have an agent interview you,
#    or refine an existing draft collaboratively
continuous-refactoring taste --interview --with codex --model gpt-5
continuous-refactoring taste --refine --with codex --model gpt-5

# 3. Do one pass
continuous-refactoring run-once \
  --with codex --model gpt-5 \
  --extensions .py

# 4. Or run the loop over a batch of targets
continuous-refactoring run \
  --with claude --model claude-opus-4-6 --default-effort high \
  --globs 'src/**/*.py' \
  --max-refactors 10 \
  --max-attempts 2 \
  --sleep 5
```

Active taste agent modes require `--with` and `--model`; taste agent sessions
always run at fixed `medium` effort.

## Subcommands

| Command | What it does |
|---|---|
| `init` | Registers this directory as a project, creates a default `taste.md`, and can store `--live-migrations-dir` or `--in-repo-taste`. |
| `taste` | Prints the active taste file path. Add `--interview` to have an agent author it, `--refine` to iteratively improve an existing taste doc, `--upgrade` to refresh stale taste dimensions, `--global` for the shared file, and `--force` to let `--interview` overwrite custom content after writing a `.bak`. Active agent modes require `--with` and `--model`, then run at fixed `medium` effort. |
| `run-once` | Single pass on one resolved target. No retry. If there is a diff and validation passes, it commits locally and prints the diffstat. |
| `run` | The loop. Iterates refactor actions, retries on failure, and commits successful changes locally. Add `--focus-on-live-migrations` to bypass targeting and work only on eligible live migrations. |
| `upgrade` | Checks that the global config manifest is current, rewrites it idempotently, and warns if the global taste file is stale. |
| `migration list` | Lists visible migrations. Add `--status <status>` or `--awaiting-review` to filter. |
| `migration doctor <slug-or-path>` | Validates one visible migration's consistency. |
| `migration doctor --all` | Validates every visible migration plus internal transaction state. |
| `migration review <slug-or-path>` | Starts staged review for a migration awaiting human review. Requires `--with` and `--model`; review runs at fixed internal `high` effort. |
| `migration refine <slug-or-path>` | Records feedback for a planning or unexecuted ready migration and runs one staged planning revision. Requires `--message <text>` or `--file <path>`, plus `--with` and `--model`; refine runs at fixed internal `high` effort. Add `--show-agent-logs` to mirror the planning agent. |

Legacy `review list` remains a compatibility shortcut for `migration list --awaiting-review`.

## Targeting / Useful flags

### Target selection

Target resolution is first-match-wins:
`--targets` > `--globs` > `--extensions` > `--paths`

These flags are not mutually exclusive, but only the highest-priority populated source is used.

- `--targets path/to/targets.jsonl` — explicit finite list; one JSON object per line with `description`, `files`, optional `scoping`, `model-override`, `effort-override`. Effort overrides use `low`, `medium`, `high`, or `xhigh`. If `--max-refactors` is omitted, `run` processes the file once and stops.
- `--globs 'src/**/*.py:tests/**/*.py'` — colon-separated globs matched once against tracked files from `git ls-files`; each refactor action samples one matched file, so files can repeat.
- `--extensions .py,.ts` — shorthand that expands to `**/*.py`, `**/*.ts` against tracked files from `git ls-files`; each refactor action samples one matched file, so files can repeat.
- `--paths a.py:b.py` — literal user-provided paths, all treated as one grouped target; each refactor action reuses that group.
- `--scope-instruction "clean up the auth module"` — extra free-text scoping. If selected file patterns resolve nothing, this becomes the useful fallback context.

If `--globs` or `--extensions` match no tracked files and there is no
`--scope-instruction`, `run` completes successfully with zero refactor actions;
`run-once` falls back to a no-file `general refactoring` target. `--paths` is
literal input and is not filtered through `git ls-files`.

If you provide none of `--targets`, `--globs`, `--extensions`, or `--paths`,
then `run` and `run-once` require `--scope-instruction`; the driver still
random-samples tracked files from `git ls-files` for each action and uses the
scope text as context for that target.

### Migrations & taste flags

- `init --live-migrations-dir PATH` — enables the larger-refactoring workflow for this project. The path is stored repo-relative in the project registry and created if missing.
- `init --in-repo-taste [PATH]` — stores this project's taste file in the repo and remembers the repo-relative path. Defaults to `.continuous-refactoring/taste.md`; re-run `init --in-repo-taste ...` to choose a different path.
- `migration list` — shows visible migrations; `--awaiting-review` narrows to human-review handoffs.
- `migration doctor <slug-or-path>` / `migration doctor --all` — read-only consistency checks. Doctor reports problems; it does not repair them.
- `migration review <slug-or-path> --with ... --model ...` — resolves an `awaiting_human_review` migration through a staged workspace at fixed internal `high` effort.
- `migration refine <slug-or-path> (--message <text>|--file <path>) --with ... --model ... [--show-agent-logs]` — adds user feedback to a planning or unexecuted ready migration and resumes planning through the `revise` step when reopening ready work at fixed internal `high` effort.
- `taste --refine --with ... --model ...` — opens a collaborative editing session for the taste file. The agent keeps refining until you tell it to write, then the session ends automatically after the settled write.
- `taste --upgrade --with ... --model ...` — re-interviews for taste dimensions added since your last version. No-op when already current; use `taste --refine` if you want to rework the doc anyway.
- Taste agent sessions always use fixed `medium` effort.
- `taste --force` — only applies to `--interview`; it allows a customized taste file to be overwritten after backing it up to `taste.md.bak`.

Canonical migration commands:

```bash
continuous-refactoring migration list
continuous-refactoring migration list --status planning
continuous-refactoring migration list --awaiting-review
continuous-refactoring migration doctor <slug-or-path>
continuous-refactoring migration doctor --all
continuous-refactoring migration review <slug-or-path> --with codex --model gpt-5
continuous-refactoring migration refine <slug-or-path> --message "split the risky phase" --with codex --model gpt-5
continuous-refactoring migration refine <slug-or-path> --file feedback.md --with codex --model gpt-5
```

### Shared `run` / `run-once` flags

- `--with`, `--model` — required agent backend/model selection.
- `--default-effort` — default effort for run calls. Defaults to `low`. Valid labels are `low`, `medium`, `high`, `xhigh`.
- `--max-allowed-effort` — cap for target overrides and migration escalation. Defaults to `xhigh`.
- `--repo-root PATH` — repository root; defaults to the current directory.
- `--validation-command` — defaults to `uv run pytest`. This is parsed with `shlex.split` and run without a shell, so simple commands like `pytest -q` work, but shell syntax such as `cmd && cmd`, pipes, redirects, or leading `VAR=value` assignments is not interpreted. Put compound validation in a script.
- `--timeout` — per-agent-call timeout in seconds.
- `--show-agent-logs` / `--show-command-logs` — mirror output to your terminal instead of just logging.
- `--refactoring-prompt` — override the default refactoring prompt.
- `--fix-prompt` — override the retry amendment prompt. Useful for `run`; accepted by `run-once` for flag symmetry.

### `run`-only flags

- `--max-attempts N` — per-action retry budget. `1` = no retry, `0` = unlimited (which means permanently broken actions will never give up).
- `--max-refactors N` — cap the number of refactor actions per run. Required unless you use `--targets` or `--focus-on-live-migrations`.
- `--focus-on-live-migrations` — bypass target selection and `--max-refactors`; iterate eligible live migrations until they are done, deferred, blocked, or the failure budget trips.
- `--max-consecutive-failures N` — bail after N actions fail in a row. Default 3.
- `--sleep SECONDS` — pause between completed actions. Useful when you want a long batch without hammering the repo or your agent budget.
- `--commit-message-prefix TEXT` — subject prefix for successful refactor or migration-plan commits. Default `continuous refactor`.

## Safety behaviors

- Refuses to start with a dirty worktree.
- Runs on the current branch. Commits land there.
- Successful commits include a `Why:` body section from the agent's reported rationale, plus validation context when available.
- `run-once`, `run`, and focused live-migration runs baseline your validation command before touching anything. If the baseline is already red, they stop.
- On a failed attempt, resets back to the pre-attempt HEAD and cleans workspace changes before retrying or moving on.
- Watchdog kills any agent or test process that's been silent for 5 minutes.

## Where the artifacts live

Each run writes to `$TMPDIR/continuous-refactoring/<run-id>/`:

- `summary.json` — rolling status, counts, per-attempt stats
- `events.jsonl` — structured event log with call roles such as
  `scope-expansion`, `classify`, `planning.<step>`, `planning.publish`,
  `phase.ready-check`, `phase.execute`, and `phase.validation`
- `run.log` — human-readable log
- `attempt-NNN/[retry-NN/]refactor/` — per-attempt agent + test stdout/stderr
- `baseline/initial/` — baseline validation stdout/stderr before work starts
- `classify/` — classifier agent stdout/stderr
- `scope-expansion/` — scope candidates, selection, and bypass reason
- `attempt-NNN/[retry-NN/]planning/<step>/` — planning agent stdout/stderr for
  migration planning steps
- `phase-ready-check/` — phase precondition agent stdout/stderr
- `attempt-NNN/[retry-NN/]phase-execute/` — phase agent and validation logs
- `migration-probes/action-NNN/` — migration probe logs during normal `run`
  actions, including planning, phase ready-checks, and phase execution

Mixed-effort runs are auditable: summaries and call events record the default effort, max allowed effort, requested effort, effective effort, source, and whether the request was capped.

The path prints at startup. Grep it when something goes sideways. Failed
non-commit decisions also write durable XDG snapshots under the project failure
directory, usually
`~/.local/share/continuous-refactoring/projects/<uuid>/failures/`.

## Taste files

The taste file is a short bullet list of your refactoring preferences. It gets injected into every agent prompt.

- Project taste: `~/.local/share/continuous-refactoring/projects/<uuid>/taste.md`, or the repo-local path chosen with `init --in-repo-taste [PATH]`
- Global taste: `~/.local/share/continuous-refactoring/global/taste.md`

Project taste wins over global. Use `taste` to print the active path, `taste --interview --with ... --model ...` to bootstrap one, `taste --refine --with ... --model ...` to rework it with an agent, or edit the file directly any time.

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
2. **Plan** — for `needs-plan` targets, each automation action runs exactly one planning step: approaches, pick-best, expand, review, optional revise/review-2, then final-review. Accepted steps update `.planning/state.json`, store stdout under `.planning/stages/`, and publish through a staged transaction. Failed current-step output stays in run artifacts and is not resume input.
3. **Execute** — each phase is a self-contained unit of work. The tick picks the oldest eligible migration, checks whether its current phase precondition is satisfied, and executes it on the current branch. Phase completion is judged against the phase file's `## Definition of Done`; commit message identifies the migration as `migration/<name>/<phase-file>.md`.

### Migration directory layout

```
<live-migrations-dir>/
  <migration-name>/
    manifest.json          # status, phases, wake-up schedule
    .planning/
      state.json           # durable planning cursor and accepted step refs
      stages/              # accepted planning stdout, suffixed on repeats
    plan.md                # the expanded plan
    approaches/            # candidate approaches considered during planning
    phase-1-<name>.md      # per-phase specification
    phase-2-<name>.md
    ...
  __transactions__/        # internal staged publish state
  __intentional_skips__/   # migrations rejected at final review
```

Do not edit `.planning/` or `__transactions__/` by hand. Use `migration doctor` when the shape looks wrong.

### Wake-up rules

Migrations don't run on every tick. The scheduler now separates **activity** from
**retry cooldown**:

- `last_touch` records the latest migration activity.
- `cooldown_until` gates repeated checks only after the migration was deferred or
  blocked.

A migration is eligible when **all** of:

- Any `cooldown_until` has elapsed.
- Either `wake_up_on` is unset, `wake_up_on` has elapsed, or the migration has
  been stale for ≥7 days.

That means successful phase execution does **not** make the next phase wait 6
hours. Phases whose preconditions are already satisfied can advance back-to-back
in the same run until the migration is actually blocked. The 6-hour cooldown
still applies after `ready: no`, future wake-ups, unverifiable phases, or
similar deferrals so the loop does not hammer stuck migrations.

### Phase model

Each migration moves through phases sequentially.

- The manifest stores each phase's **precondition** — what must already be true before execution may start.
- Each phase markdown file stores its **Definition of Done** under `## Definition of Done` — what must be true for that phase to count as completed.
- A phase may declare optional `required_effort` and `effort_reason` in the manifest. The driver escalates up to `--max-allowed-effort`; if a phase needs more, the phase is deferred without failing the run and can be picked up by a later higher-budget run.

Before executing a phase, a ready-check agent verifies that the current phase precondition is met. Phase preconditions are for phase-local facts only; the harness owns baseline-green validation before work and full validation after phase execution. Possible outcomes:

- **ready: yes** — phase executes; on green tests, the phase is marked done, any prior deferral markers are cleared, and the migration advances immediately to the next phase.
- **ready: no** — manifest activity is bumped, a retry cooldown is started, and a future `wake_up_on` is recorded when needed; the tick moves on.
- **ready: unverifiable** — the migration is marked `awaiting_human_review` and put on cooldown. Automated migration ticks skip migrations awaiting human review until review clears the flag. Use `migration list --awaiting-review` to find it and `migration review <slug-or-path> --with ... --model ...` to resolve it interactively.

Human-facing migration references use the relative phase spec path, for example `phase-2-failure-report.md`. The manifest cursor stores the phase `name`, not a numeric index.

### What the CLI doesn't do

Rollout mechanics — feature flag names, deploy tooling, metric dashboards, canary analysis — are the coding agent's responsibility, not a CLI-visible concern. The CLI manages the planning and phased execution workflow; the agent writes whatever rollout code the plan calls for.
