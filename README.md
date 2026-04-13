# continuous-refactoring

A CLI that hands your repo to a coding agent (Codex or Claude) and asks it to make small, safe cleanup commits — one at a time, on a fresh branch, gated by your test suite.

Think of it as a supervised janitor loop: the agent proposes a cleanup, your tests decide if it stays.

## What it does

- Picks a target (a file, a glob, a random tracked file, or a scope you describe).
- Runs the agent with a refactoring prompt + your "taste" guidelines.
- Runs your validation command (default: `uv run pytest`).
- If green and there's a diff, commits and pushes. If red, reverts and moves on.
- Repeats until it runs out of targets, hits the retry budget, or stacks too many failures.

## Requirements

- Python 3.10+
- [uv](https://github.com/astral-sh/uv)
- `codex` or `claude` CLI on your `PATH` (whichever backend you pick)
- A git repo with a clean worktree and a `main` or `master` branch

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

# 2. (Optional) Write your refactoring taste — either edit the file or have an agent interview you
continuous-refactoring taste --interview --with codex --model gpt-5 --effort high

# 3. Do one pass
continuous-refactoring run-once \
  --with codex --model gpt-5 --effort high \
  --extensions .py

# 4. Or run the loop over a batch of targets
continuous-refactoring run \
  --with claude --model claude-opus-4-6 --effort high \
  --globs 'src/**/*.py' \
  --max-attempts 2
```

## Subcommands

| Command | What it does |
|---|---|
| `init` | Registers this directory as a project; creates a default `taste.md`. |
| `taste` | Prints the active taste file path. Add `--interview` to have an agent author it with you. `--global` targets the shared user-level file. |
| `run-once` | Single pass on one target. No retry, no push. Leaves the branch for you to review. |
| `run` | The loop. Iterates targets, retries on failure, commits and pushes greens. |

## Targeting

Pick *one* of these to tell the tool what to clean up:

- `--targets path/to/targets.jsonl` — explicit list; one JSON object per line with `description`, `files`, optional `scoping`, `model-override`, `effort-override`.
- `--globs 'src/**/*.py:tests/**/*.py'` — colon-separated globs; each matched file becomes its own target.
- `--extensions .py,.ts` — shorthand that expands to `**/*.py`, `**/*.ts`.
- `--paths a.py:b.py` — literal paths, all treated as one target.
- `--scope-instruction "clean up the auth module"` — free-text scope, no file list.

If none of these match any tracked files, you must provide `--scope-instruction` as a fallback.

## Useful flags

- `--validation-command` — defaults to `uv run pytest`. Swap it for whatever keeps your repo honest.
- `--max-attempts N` — per-target retry budget. `1` = no retry, `0` = unlimited (⚠️ loops forever on broken targets).
- `--max-refactors N` — cap the number of targets per run.
- `--max-consecutive-failures N` — bail after N targets fail in a row. Default 3.
- `--no-push` — keep commits local.
- `--timeout` — per-agent-call timeout in seconds.
- `--show-agent-logs` / `--show-command-logs` — mirror output to your terminal instead of just logging.
- `--refactoring-prompt` / `--fix-prompt` — swap in your own prompt files.

## Safety behaviors

- Refuses to start with a dirty worktree.
- Runs every pass on a fresh branch (`refactor-<timestamp>` or `cr/<timestamp>`).
- Baselines your tests before touching anything — if the baseline is already red, it stops.
- On a failed attempt: undoes the commit (if any) and hard-resets the workspace before retrying or moving on.
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

Project taste wins over global. Use `taste --interview` to bootstrap one; edit the file directly any time.
