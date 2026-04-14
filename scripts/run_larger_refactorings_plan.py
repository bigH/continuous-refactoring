#!/usr/bin/env python3
"""Execute docs/plans/larger-refactorings.md one task at a time.

Behaviour (mirrors the plan's documented contract):

* Reads the plan, respects the top-level ``Status:`` line.
* ``Status: failed`` prints the reason, exits 1.
* ``Status: awaiting ...`` prints what's pending, exits 0.
* Otherwise finds the next task with ``done: false`` and every ``blocked_by``
  entry already done. Dispatches a coding agent (prompt built from
  ``title`` / ``touches`` / ``review_criteria``), then a review agent that
  checks the criteria, fixes small issues, and runs the validation command.
* On success: flips ``done: true`` in the plan and commits plan + code as one
  commit, then loops to the next task.
* On failure (coding agent non-zero, review fails past the retry budget, or
  final validation red): sets ``Status: failed -- <reason>``, commits only the
  plan update, exits 1.
* Resumable: re-running picks up at the next undone unblocked task. The plan
  is the sole source of truth -- no sidecar state file.
* Operates on the current branch; never pushes.

Runtime deps: stdlib only, plus ``src/continuous_refactoring`` already in
the repo (reused for agent / git / artifact helpers).
"""
from __future__ import annotations

import argparse
import json
import re
from enum import Enum
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from continuous_refactoring.agent import (  # noqa: E402
    maybe_run_agent,
    run_tests,
    summarize_output,
)
from continuous_refactoring.artifacts import (  # noqa: E402
    CommandCapture,
    ContinuousRefactorError,
    create_run_artifacts,
)
from continuous_refactoring.git import (  # noqa: E402
    discard_workspace_changes,
    git_commit,
    repo_has_changes,
    require_clean_worktree,
)

PLAN_PATH = REPO_ROOT / "docs" / "plans" / "larger-refactorings.md"

# One task = one ```json task``` fenced block. Non-greedy body capture; both
# fences are anchored to line starts so prose mentioning ```json task``` inline
# cannot match.
TASK_BLOCK_RE = re.compile(
    r"^```json task\s*\n(?P<body>[\s\S]*?)\n^```",
    re.MULTILINE,
)
STATUS_RE = re.compile(r"^Status:\s*(?P<value>.+?)\s*$", re.MULTILINE)


class PlanStatus(str, Enum):
    TODO = "todo"
    AWAITING = "awaiting"
    FAILED = "failed"


def parse_plan_status(raw: str) -> PlanStatus:
    normalized = raw.strip().lower()
    if normalized.startswith(PlanStatus.TODO.value):
        return PlanStatus.TODO
    if normalized.startswith(PlanStatus.AWAITING.value):
        return PlanStatus.AWAITING
    if normalized.startswith(PlanStatus.FAILED.value):
        return PlanStatus.FAILED
    raise ValueError(f"unrecognized plan status: {raw!r}")

REVIEW_OK = "REVIEW_OK"
REVIEW_FAILED = "REVIEW_FAILED"

DEFAULT_TIMEOUT_SECONDS = 1800
MAX_ATTEMPTS_PER_TASK = 2  # coding + review pair per attempt


@dataclass
class Task:
    id: str
    title: str
    type: str
    touches: list[str]
    blocked_by: list[str]
    review_criteria: list[str]
    done: bool
    raw: str  # body text between the fences, for in-place rewrite
    span: tuple[int, int]  # (start, end) in plan text -- body only


@dataclass
class Plan:
    path: Path
    text: str
    status: str
    tasks: list[Task]


# ---------------------------------------------------------------------------
# Parsing / rewriting the plan
# ---------------------------------------------------------------------------


def parse_plan(text: str) -> Plan:
    status_match = STATUS_RE.search(text)
    if status_match is None:
        raise SystemExit("plan has no top-level `Status:` line.")
    status = status_match.group("value").strip()

    tasks: list[Task] = []
    for block_match in TASK_BLOCK_RE.finditer(text):
        body = block_match.group("body")
        try:
            data = json.loads(body)
        except json.JSONDecodeError as error:
            raise SystemExit(
                f"task block is not valid JSON at offset {block_match.start()}: {error}"
            ) from error
        try:
            tasks.append(
                Task(
                    id=str(data["id"]),
                    title=str(data["title"]),
                    type=str(data["type"]),
                    touches=list(data.get("touches", [])),
                    blocked_by=list(data.get("blocked_by", [])),
                    review_criteria=list(data.get("review_criteria", [])),
                    done=bool(data["done"]),
                    raw=body,
                    span=(block_match.start("body"), block_match.end("body")),
                )
            )
        except KeyError as error:
            raise SystemExit(
                f"task block at offset {block_match.start()} missing required field {error}."
            ) from error
    return Plan(path=PLAN_PATH, text=text, status=status, tasks=tasks)


def validate_plan(plan: Plan) -> None:
    ids = [t.id for t in plan.tasks]
    if len(ids) != len(set(ids)):
        raise SystemExit("plan has duplicate task ids.")
    id_set = set(ids)
    by_id = {t.id: t for t in plan.tasks}
    for t in plan.tasks:
        for dep in t.blocked_by:
            if dep not in id_set:
                raise SystemExit(f"task {t.id} references unknown dependency {dep}.")
    # DFS cycle detection
    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(node: str, chain: tuple[str, ...]) -> None:
        if node in visited:
            return
        if node in visiting:
            path = " -> ".join(chain + (node,))
            raise SystemExit(f"dependency cycle: {path}.")
        visiting.add(node)
        for dep in by_id[node].blocked_by:
            dfs(dep, chain + (node,))
        visiting.discard(node)
        visited.add(node)

    for task in plan.tasks:
        dfs(task.id, ())


def pick_next_task(plan: Plan) -> Task | None:
    done_ids = {t.id for t in plan.tasks if t.done}
    for task in plan.tasks:
        if task.done:
            continue
        if all(dep in done_ids for dep in task.blocked_by):
            return task
    return None


_DONE_FALSE_RE = re.compile(r'"done"\s*:\s*false')


def rewrite_task_done(plan_text: str, task: Task) -> str:
    """Flip ``"done": false`` to ``"done": true`` inside a single task body.

    Targeted substitution rather than a JSON round-trip so the body's original
    formatting -- compact arrays, non-ASCII characters (em-dash, arrow), key
    ordering -- survives byte-for-byte.
    """
    start, end = task.span
    body = plan_text[start:end]
    new_body, count = _DONE_FALSE_RE.subn('"done": true', body, count=1)
    if count != 1:
        raise SystemExit(
            f"task {task.id}: expected one `\"done\": false` to flip, found {count}."
        )
    return plan_text[:start] + new_body + plan_text[end:]


def rewrite_status(plan_text: str, new_status: str) -> str:
    replacement = f"Status: {new_status}"
    return STATUS_RE.sub(replacement, plan_text, count=1)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _bullet(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- (none)"


def build_coding_prompt(task: Task, validation_command: str) -> str:
    return textwrap.dedent(
        f"""\
        You are executing one task from docs/plans/larger-refactorings.md.
        Read that plan in full before touching any file.

        Task id: {task.id}
        Title: {task.title}
        Type: {task.type}

        Files / globs in scope (the plan's `touches` field):
        {_bullet(task.touches)}

        Review criteria (your work is judged on these):
        {_bullet(task.review_criteria)}

        Rules:
        - Stay inside the declared scope. If a criterion forces an edit outside
          `touches`, keep it minimal and note the reason in your final summary.
        - Match the existing code style in src/continuous_refactoring/: short
          functions, types everywhere, minimal comments, stdlib-only.
        - Do NOT edit docs/plans/larger-refactorings.md -- the orchestrator
          rewrites it on your behalf.
        - Do NOT create git commits -- the orchestrator commits on success.
        - Leave the workspace with `{validation_command}` passing.
        - End your run with a short plain-text summary of the changes you made.
        """
    )


def build_review_prompt(task: Task, validation_command: str) -> str:
    return textwrap.dedent(
        f"""\
        You are the review agent for task {task.id} ({task.title}).
        The coding agent has just finished. Your only job is to decide whether
        this task is done; you may fix small issues in place.

        Review criteria:
        {_bullet(task.review_criteria)}

        Protocol:
        1. Inspect the workspace: `git status`, `git diff`, read the edited files.
        2. Verify every review criterion against the real repo state (not the
           coding agent's claims). Be strict.
        3. Fix SMALL issues yourself (missing import, formatting, typo, a
           misspelled symbol, a missing short test). Do not redesign.
        4. Run `{validation_command}`. Confirm it exits 0.
        5. Do NOT edit docs/plans/larger-refactorings.md.
        6. Do NOT create git commits.

        Output contract (the orchestrator reads the last non-blank line only):
        - Print `{REVIEW_OK}` on its own line when every criterion is satisfied
          and the validation command passed.
        - Print `{REVIEW_FAILED}: <short reason>` on its own line otherwise.
        """
    )


def build_retry_prompt(task: Task, validation_command: str, prior_reason: str) -> str:
    retry_tail = textwrap.dedent(
        f"""

        --- retry context ---
        The previous attempt was rejected by the review agent:
        {prior_reason}

        Fix only what the review reason points at. Keep the scope minimal.
        """
    )
    return build_coding_prompt(task, validation_command) + retry_tail


# ---------------------------------------------------------------------------
# Agent dispatch
# ---------------------------------------------------------------------------


def _dispatch(
    *,
    agent: str,
    model: str,
    effort: str,
    prompt: str,
    stdout_path: Path,
    stderr_path: Path,
    last_message_path: Path | None,
    mirror: bool,
    timeout: int,
) -> CommandCapture:
    return maybe_run_agent(
        agent=agent,
        model=model,
        effort=effort,
        prompt=prompt,
        repo_root=REPO_ROOT,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        last_message_path=last_message_path,
        mirror_to_terminal=mirror,
        timeout=timeout,
    )


def _extract_claude_final_message(source: str) -> str | None:
    """Claude stream-json output wraps the final assistant message inside
    ``{"type":"result","result":"..."}``; return that field so the sentinel
    scanner sees plain text rather than JSON-wrapped events.
    """
    for raw_line in reversed(source.splitlines()):
        idx = raw_line.find('{"type":"result"')
        if idx < 0:
            continue
        try:
            event = json.loads(raw_line[idx:])
        except json.JSONDecodeError:
            continue
        text = event.get("result")
        return text if isinstance(text, str) else None
    return None


def _scan_for_sentinel(text: str) -> tuple[bool, str] | None:
    for raw_line in reversed(text.splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        if line == REVIEW_OK:
            return True, ""
        if line.startswith(REVIEW_FAILED):
            reason = line[len(REVIEW_FAILED):].lstrip(" :-") or "unspecified"
            return False, reason
    return None


def _review_verdict(
    result: CommandCapture,
    last_message_path: Path | None = None,
) -> tuple[bool, str]:
    """Decide the review verdict from agent output.

    Codex writes its final assistant message to ``last_message_path`` via
    ``--output-last-message`` and NOT to stdout, so check that file first.
    Claude emits stream-json, where the sentinel is buried inside a
    ``{"type":"result","result":"..."}`` envelope -- unwrap that before
    scanning. Fall back to a plain-text scan so either format still works.
    """
    sources: list[str] = []
    if last_message_path is not None and last_message_path.exists():
        sources.append(
            last_message_path.read_text(encoding="utf-8", errors="replace")
        )
    sources.append(result.stdout)
    sources.append(result.stderr)

    for source in sources:
        claude_final = _extract_claude_final_message(source)
        if claude_final is not None:
            verdict = _scan_for_sentinel(claude_final)
            if verdict is not None:
                return verdict
        verdict = _scan_for_sentinel(source)
        if verdict is not None:
            return verdict
    return False, "review agent emitted no REVIEW_OK/REVIEW_FAILED sentinel."


# ---------------------------------------------------------------------------
# Task execution
# ---------------------------------------------------------------------------


@dataclass
class TaskOutcome:
    ok: bool
    reason: str  # empty when ok


def _attempt_dir(artifacts_root: Path, task: Task, attempt: int, role: str) -> Path:
    path = artifacts_root / f"task-{task.id}" / f"attempt-{attempt:02d}" / role
    path.mkdir(parents=True, exist_ok=True)
    return path


def _last_message_path(args: argparse.Namespace, dirpath: Path) -> Path | None:
    return dirpath / "agent-last-message.md" if args.agent == "codex" else None


def execute_task(
    task: Task,
    args: argparse.Namespace,
    artifacts_root: Path,
) -> TaskOutcome:
    prior_reason = ""
    for attempt in range(1, MAX_ATTEMPTS_PER_TASK + 1):
        discard_workspace_changes(REPO_ROOT)

        coding_dir = _attempt_dir(artifacts_root, task, attempt, "coding")
        coding_prompt = (
            build_retry_prompt(task, args.validation_command, prior_reason)
            if prior_reason
            else build_coding_prompt(task, args.validation_command)
        )
        coding = _dispatch(
            agent=args.agent,
            model=args.model,
            effort=args.effort,
            prompt=coding_prompt,
            stdout_path=coding_dir / "agent.stdout.log",
            stderr_path=coding_dir / "agent.stderr.log",
            last_message_path=_last_message_path(args, coding_dir),
            mirror=args.show_agent_logs,
            timeout=args.timeout,
        )
        if coding.returncode != 0:
            prior_reason = (
                f"coding agent exited {coding.returncode}:\n"
                f"{summarize_output(coding)}"
            )
            continue

        review_dir = _attempt_dir(artifacts_root, task, attempt, "review")
        review_last_message = _last_message_path(args, review_dir)
        review = _dispatch(
            agent=args.agent,
            model=args.model,
            effort=args.effort,
            prompt=build_review_prompt(task, args.validation_command),
            stdout_path=review_dir / "agent.stdout.log",
            stderr_path=review_dir / "agent.stderr.log",
            last_message_path=review_last_message,
            mirror=args.show_agent_logs,
            timeout=args.timeout,
        )
        if review.returncode != 0:
            prior_reason = (
                f"review agent exited {review.returncode}:\n"
                f"{summarize_output(review)}"
            )
            continue

        ok, reason = _review_verdict(review, review_last_message)
        if not ok:
            prior_reason = reason
            continue

        # Orchestrator-side validation pass as a final gate. Trust, then verify.
        gate_dir = _attempt_dir(artifacts_root, task, attempt, "final-validation")
        validation = run_tests(
            args.validation_command,
            REPO_ROOT,
            stdout_path=gate_dir / "tests.stdout.log",
            stderr_path=gate_dir / "tests.stderr.log",
            mirror_to_terminal=args.show_command_logs,
        )
        if validation.returncode != 0:
            prior_reason = (
                "review passed but final validation failed:\n"
                f"{summarize_output(validation)}"
            )
            continue

        return TaskOutcome(ok=True, reason="")

    return TaskOutcome(
        ok=False,
        reason=f"task {task.id} failed after {MAX_ATTEMPTS_PER_TASK} attempts: {prior_reason}",
    )


# ---------------------------------------------------------------------------
# Git wrapping around task outcome
# ---------------------------------------------------------------------------


def commit_success(task: Task, plan_text_after: str) -> str:
    PLAN_PATH.write_text(plan_text_after, encoding="utf-8")
    if not repo_has_changes(REPO_ROOT):
        raise ContinuousRefactorError(
            f"task {task.id} reported success but produced no git changes."
        )
    message = f"plan/{task.id}: {task.title}"
    return git_commit(REPO_ROOT, message)


def commit_failure(task: Task, reason: str, plan_text: str) -> str | None:
    discard_workspace_changes(REPO_ROOT)
    short = _single_line(reason)
    new_text = rewrite_status(plan_text, f"failed -- {short}")
    PLAN_PATH.write_text(new_text, encoding="utf-8")
    if not repo_has_changes(REPO_ROOT):
        return None
    return git_commit(REPO_ROOT, f"plan: {task.id} failed -- {short}")


def _single_line(text: str, limit: int = 200) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 3] + "..."


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute docs/plans/larger-refactorings.md end-to-end."
    )
    parser.add_argument(
        "--with",
        dest="agent",
        choices=("codex", "claude"),
        required=True,
        help="Agent backend used for coding + review passes.",
    )
    parser.add_argument("--model", required=True, help="Model name.")
    parser.add_argument("--effort", required=True, help="Effort/reasoning level.")
    parser.add_argument(
        "--validation-command",
        default="uv run pytest",
        help="Validation command run after review (default: uv run pytest).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Timeout per agent call (seconds; default {DEFAULT_TIMEOUT_SECONDS}).",
    )
    parser.add_argument(
        "--show-agent-logs",
        action="store_true",
        help="Mirror agent stdout/stderr to this terminal.",
    )
    parser.add_argument(
        "--show-command-logs",
        action="store_true",
        help="Mirror validation-command output to this terminal.",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=None,
        help="Stop after N successful tasks in this run (default: all).",
    )
    return parser.parse_args(argv)


def _recover_interrupted_success(repo_root: Path) -> str | None:
    """Commit a pending success left behind by a prior run that crashed between
    rewriting the plan and committing it. Detects the case where the on-disk plan
    has a ``done: true`` flip not yet present at HEAD and commits it together
    with whatever code changes accompany it.
    """
    if not repo_has_changes(repo_root):
        return None

    plan_rel = PLAN_PATH.relative_to(repo_root).as_posix()
    result = subprocess.run(
        ["git", "show", f"HEAD:{plan_rel}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None

    try:
        head_plan = parse_plan(result.stdout)
        disk_plan = parse_plan(PLAN_PATH.read_text(encoding="utf-8"))
    except SystemExit:
        return None

    head_done = {t.id: t.done for t in head_plan.tasks}
    flipped = [t for t in disk_plan.tasks if t.done and not head_done.get(t.id, False)]
    if len(flipped) != 1:
        return None

    task = flipped[0]
    sha = git_commit(repo_root, f"plan/{task.id}: {task.title}")
    print(f"recovered interrupted task {task.id}; committed as {sha}.")
    return sha


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not PLAN_PATH.exists():
        print(f"plan not found: {PLAN_PATH}", file=sys.stderr)
        return 1

    plan = parse_plan(PLAN_PATH.read_text(encoding="utf-8"))
    validate_plan(plan)
    try:
        status = parse_plan_status(plan.status)
    except ValueError as exc:
        print(f"unrecognized plan status: {plan.status!r}", file=sys.stderr)
        return 1

    if status is PlanStatus.FAILED:
        print(f"plan is failed: {plan.status}", file=sys.stderr)
        return 1
    if status is PlanStatus.AWAITING:
        print(f"plan is blocked: {plan.status}")
        return 0
    if status is not PlanStatus.TODO:
        print(f"unrecognized plan status: {plan.status!r}", file=sys.stderr)
        return 1

    _recover_interrupted_success(REPO_ROOT)
    require_clean_worktree(REPO_ROOT)

    artifacts = create_run_artifacts(
        REPO_ROOT,
        agent=args.agent,
        model=args.model,
        effort=args.effort,
        test_command=args.validation_command,
    )
    artifacts.log(
        "INFO",
        f"orchestrator started; artifacts at {artifacts.root}",
        event="orchestrator_started",
        started_at=datetime.now().astimezone().isoformat(timespec="seconds"),
    )

    tasks_done_this_run = 0
    while True:
        plan_text = PLAN_PATH.read_text(encoding="utf-8")
        plan = parse_plan(plan_text)
        validate_plan(plan)
        try:
            status = parse_plan_status(plan.status)
        except ValueError:
            artifacts.log(
                "ERROR",
                f"plan status is now unrecognized: {plan.status!r}",
                event="invalid_status",
            )
            artifacts.finish("failed", error_message="unrecognized plan status")
            return 1

        if status is not PlanStatus.TODO:
            artifacts.log("INFO", f"plan status is now {plan.status!r}; stopping.")
            return 0 if status is PlanStatus.AWAITING else 1

        task = pick_next_task(plan)
        if task is None:
            if all(t.done for t in plan.tasks):
                artifacts.log("INFO", "all tasks done.")
                print("All tasks done.")
                artifacts.finish("completed")
                return 0
            reason = "no unblocked task but plan incomplete (stuck dependency chain)."
            artifacts.log("ERROR", reason, event="stuck")
            commit_failure(plan.tasks[0], reason, plan_text)
            artifacts.finish("failed", error_message=reason)
            return 1

        artifacts.log(
            "INFO",
            f"working task {task.id}: {task.title}",
            event="task_started",
            task_id=task.id,
        )

        try:
            outcome = execute_task(task, args, artifacts.root)
        except ContinuousRefactorError as error:
            outcome = TaskOutcome(ok=False, reason=str(error))
        except KeyboardInterrupt:
            artifacts.log("WARN", "interrupted by user.", event="interrupted")
            discard_workspace_changes(REPO_ROOT)
            artifacts.finish("interrupted")
            return 130

        if not outcome.ok:
            sha = commit_failure(task, outcome.reason, plan_text)
            artifacts.log(
                "ERROR",
                f"task {task.id} failed: {outcome.reason}",
                event="task_failed",
                task_id=task.id,
                commit=sha,
            )
            artifacts.finish("failed", error_message=outcome.reason)
            print(f"task {task.id} failed: {outcome.reason}", file=sys.stderr)
            return 1

        new_plan_text = rewrite_task_done(plan_text, task)
        try:
            sha = commit_success(task, new_plan_text)
        except ContinuousRefactorError as error:
            reason = f"{task.id} succeeded but commit_success failed: {error}"
            artifacts.log("ERROR", reason, event="commit_failed", task_id=task.id)
            # Put the plan back to its pre-success text, then mark failed.
            PLAN_PATH.write_text(plan_text, encoding="utf-8")
            commit_failure(task, reason, plan_text)
            artifacts.finish("failed", error_message=reason)
            return 1

        tasks_done_this_run += 1
        artifacts.log(
            "INFO",
            f"task {task.id} done; commit {sha}.",
            event="task_done",
            task_id=task.id,
            commit=sha,
        )
        print(f"task {task.id} done ({sha}).")

        if args.max_tasks is not None and tasks_done_this_run >= args.max_tasks:
            artifacts.log(
                "INFO",
                f"reached --max-tasks={args.max_tasks}; stopping.",
                event="max_tasks_reached",
            )
            artifacts.finish("completed")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
