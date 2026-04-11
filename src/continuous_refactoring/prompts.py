from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from continuous_refactoring.targeting import Target

__all__ = [
    "CHOSEN_SCOPE_PATTERN",
    "DEFAULT_FIX_AMENDMENT",
    "DEFAULT_REFACTORING_PROMPT",
    "REQUIRED_PREAMBLE",
    "SUMMARY_UNKNOWN",
    "TARGET_HEADER_PATTERN",
    "TARGET_LINE_PATTERN",
    "compose_full_prompt",
    "compose_refactor_prompt",
    "describe_target",
    "extract_chosen_target",
    "normalize_target",
    "prompt_file_text",
    "resolve_phase_target",
]

from continuous_refactoring.artifacts import CommandCapture


CHOSEN_SCOPE_PATTERN = r"(?:chosen_target|chosen_scope)"
REQUIRED_PREAMBLE = (
    "All changes must keep the project in a state where all tests pass. "
    "Do not finish unless the repository is green after your refactor."
)

DEFAULT_REFACTORING_PROMPT = """\
You are a continuous refactoring agent. Start cold. Assume no memory from prior runs and no operator context beyond this prompt and current repository state.

Mission:
Make one cohesive cleanup batch that leaves the repository cleaner, smaller,
truer, or easier to change without drifting into product work, architecture
churn, or infrastructure work.

Guardrails:
- One run equals one cohesive cleanup batch. That batch may include one primary
  simplification and one or two tightly related follow-on cleanups when they
  share the same rationale, module cluster, and validation path. Do not chain
  unrelated increments.
- A cleanup batch fixes one local invariant, maintenance hazard, dead path, or
  weak safety net in one module cluster. If the change needs multiple rationales
  or is mostly file shuffling, it is too big.
- When tradeoffs are unclear, bias toward deletion, directness, fail-fast invariants, and truthful names.
- Treat compatibility, migration, fallback, adapter, and legacy-shaped code as review targets by default.
- Preserve public, boundary, config, CLI, API, and user-visible behavior. Change it only when explicit, convergent repo evidence already supports the simpler contract. Convergent evidence means the current tests, current callers, relevant docs/spec, and recent history point the same way. If evidence is missing or conflicts, stop blocked.
- Do not rely on prior chat context. If a future run needs context, it must come from the repo or commit history.
- No major architecture changes, infra changes, framework swaps, persistence-model redesigns, speculative abstractions, broad style churn, or repo-wide rename/move campaigns.
- Local renames, moves, splits, and merges are fine only when the payoff is obvious, the scope is tight, and validation is real.
- Do not edit specs or planning docs to justify keeping or deleting code in the same run.

Discovery:
1. Read repository instructions first (`AGENTS.md` and any nearby agent guidance).
2. Discover the repo's sanctioned workflows, languages, module layout, and test entrypoints from the repo itself.
3. Check `git status`.
   - If the working tree is dirty, stop blocked. Do not rely on the driver to reset it away.
4. Inspect docs, specs, and recent history only as supporting evidence for the chosen area.
5. Identify the repo's default broad validation command and the narrowest relevant checks for the touched surface. Do not assume them.

Candidate patterns:
- dead code, dead exports, dead APIs, abandoned experiments
- compatibility branches or fallback lookups with no active need
- single-caller wrappers, dead abstractions, and misleading rollout-shaped names
- overlong functions, low-cohesion modules, and splits or merges that improve locality
- shallow mocks or weak tests that directly block a safe simplification in the same area
- exception wrapping that adds no useful signal away from real boundaries

How to choose work:
1. Find 3 candidate simplifications or small cleanup batches.
2. Prefer the candidate with a clear cleanliness payoff and a plausible validation path in this run.
3. Reject cosmetic, taste-only, or high-churn candidates.
4. If the baseline is broken, intent is ambiguous, or the needed safety net cannot be established in this area, stop blocked.

Workflow:
1. Record the candidates and choose one cleanup batch.
2. State the protected behavior or invariant.
3. Strengthen the minimal tests needed to protect that behavior.
   - Safety-net work is valid only when it directly enables this chosen batch in the same area.
   - Do not turn the run into standalone harness or framework churn.
4. Refactor the production code, including any tightly related cleanup needed to
   land the batch cleanly.
5. Run the narrowest relevant checks first.
6. Run the strongest repo-sanctioned broad check that meaningfully covers the touched surface.
   - If that broad check is baseline-red, unavailable, or its relevance cannot be shown from repo evidence, stop blocked.
7. Triage failures with evidence.
   - Regression introduced by you: fix it or revert.
   - Test encoded accidental complexity: simplify only if boundary behavior remains protected and repo evidence still supports the simpler contract.
   - Failure that predates your change: keep going only if repo evidence proves it predates the change; otherwise stop blocked.
8. Keep the batch only if it is a net improvement in clarity, truthfulness, maintenance cost, or testability.
9. If the batch is working and validated, commit it immediately as one atomic commit, then stop.
10. If not, stop without a commit.

Refactoring taste:
- Validate at the edges and stay lean in the middle.
- Keep exception translation only at real boundaries and preserve causes when translating.
- Keep comments only when they explain a real boundary contract or a genuinely deferred design issue that code alone cannot make obvious.
- Remove fallback, compat, adapter, migrated, legacy, or normalize-shaped code when evidence shows it is no longer needed.
- Merge modules when splits hurt locality more than they help. Split modules when one file hides unrelated responsibilities.

Stop when:
- one cohesive cleanup batch is done
- the next step needs product or architecture judgment
- baseline health or validation relevance is unclear
- boundary behavior or dead-code intent is ambiguous
- no high-confidence candidate remains

Output:
- `chosen_scope`
- `chosen_target` (optional compatibility alias; mirror `chosen_scope` when useful)
- `protected_behavior`
- `evidence`
- `tests_run`
- `broad_validation`
- `failure_triage` when non-empty
- `decision` (`commit`, `revert`, or `blocked`)
- `commit_sha` or `blocked_reason`
- `next_candidate`\
"""

DEFAULT_FIX_AMENDMENT = """\
After this pass, run the repository-wide checks for this repo (default `uv run pytest`).
If any check fails, stop and only retry from a clean git state.
Do not commit anything until all checks are green.\
"""

TARGET_LINE_PATTERN = re.compile(
    rf"^\s*(?:[-*]\s*)?(?:`|\*\*)?{CHOSEN_SCOPE_PATTERN}"
    rf"(?:`|\*\*)?\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)
TARGET_HEADER_PATTERN = re.compile(
    rf"^\s*(?:#+\s*)?(?:`|\*\*)?{CHOSEN_SCOPE_PATTERN}(?:`|\*\*)?\s*:?\s*$",
    re.IGNORECASE,
)
SUMMARY_UNKNOWN = "scope unavailable"


def prompt_file_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def compose_refactor_prompt(
    base_prompt: str,
    attempt: int,
    previous_failure: str | None = None,
) -> str:
    sections = [
        f"Attempt {attempt}",
        base_prompt,
        REQUIRED_PREAMBLE,
    ]
    if previous_failure:
        sections.append("Previous attempt failed tests with this output:\n")
        sections.append(previous_failure)
        sections.append(
            "Use this as context only if it helps; do not copy test output into code."
        )
        sections.append(
            "Only fix failures introduced by this refactoring pass. "
            "If a failure is not a direct consequence of your edits, "
            "do not rewrite unrelated code."
        )
    return "\n\n".join(sections)


def normalize_target(text: str) -> str:
    return " ".join(text.strip().strip("`*").split())


def extract_chosen_target(text: str) -> str | None:
    lines = text.splitlines()
    for line in lines:
        match = TARGET_LINE_PATTERN.match(line)
        if match:
            return normalize_target(match.group(1))

    for index, line in enumerate(lines):
        if not TARGET_HEADER_PATTERN.match(line):
            continue
        for candidate in lines[index + 1 :]:
            stripped = candidate.strip()
            if not stripped:
                continue
            if stripped.startswith(("-", "*")):
                stripped = stripped[1:].strip()
            return normalize_target(stripped)
    return None


def resolve_phase_target(
    agent_result: CommandCapture,
    last_message_path: Path | None,
) -> str | None:
    if last_message_path is not None and last_message_path.exists():
        target = extract_chosen_target(last_message_path.read_text(encoding="utf-8"))
        if target:
            return target
    return extract_chosen_target(agent_result.stdout) or extract_chosen_target(
        agent_result.stderr
    )


def describe_target(target: str | None) -> str:
    return target or SUMMARY_UNKNOWN


def compose_full_prompt(
    *,
    base_prompt: str,
    taste: str,
    target: Target,
    scope_instruction: str | None,
    validation_command: str,
    attempt: int,
    previous_failure: str | None = None,
) -> str:
    sections = [f"Attempt {attempt}", base_prompt, REQUIRED_PREAMBLE]
    sections.append(f"## Refactoring Taste\n{taste}")
    if target.files:
        files_text = "\n".join(f"- {f}" for f in target.files)
        sections.append(f"## Target Files\n{files_text}")
    if target.scoping or scope_instruction:
        scope = target.scoping or scope_instruction
        sections.append(f"## Scope\n{scope}")
    sections.append(f"## Validation\nRun: `{validation_command}`")
    if previous_failure:
        sections.append("Previous attempt failed tests with this output:\n")
        sections.append(previous_failure)
        sections.append(
            "Use this as context only if it helps; do not copy test output into code."
        )
        sections.append(
            "Only fix failures introduced by this refactoring pass."
        )
    return "\n\n".join(sections)
