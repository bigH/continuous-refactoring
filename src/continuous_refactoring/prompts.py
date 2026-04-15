from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from continuous_refactoring.migrations import MigrationManifest, PhaseSpec
    from continuous_refactoring.targeting import Target

__all__ = [
    "CLASSIFIER_PROMPT",
    "DEFAULT_FIX_AMENDMENT",
    "DEFAULT_REFACTORING_PROMPT",
    "INTERVIEW_PROMPT_TEMPLATE",
    "PHASE_EXECUTION_PROMPT",
    "PHASE_READY_CHECK_PROMPT",
    "PLANNING_APPROACHES_PROMPT",
    "PLANNING_EXPAND_PROMPT",
    "PLANNING_FINAL_REVIEW_PROMPT",
    "PLANNING_PICK_BEST_PROMPT",
    "PLANNING_REVIEW_PROMPT",
    "PlanningStage",
    "REQUIRED_PREAMBLE",
    "REVIEW_PERFORM_PROMPT",
    "TASTE_UPGRADE_PROMPT_TEMPLATE",
    "compose_classifier_prompt",
    "compose_full_prompt",
    "compose_interview_prompt",
    "compose_phase_execution_prompt",
    "compose_phase_ready_prompt",
    "compose_planning_prompt",
    "compose_review_perform_prompt",
    "compose_taste_upgrade_prompt",
    "prompt_file_text",
]


def _join_sections(*sections: str | None) -> str:
    return "\n\n".join(section for section in sections if section)


def _format_target_files(files: tuple[str, ...]) -> str | None:
    if not files:
        return None
    files_text = "\n".join(f"- {f}" for f in files)
    return f"## Target Files\n{files_text}"


def _first_scope(*scopes: str | None) -> str | None:
    for scope in scopes:
        if scope:
            return f"## Scope\n{scope}"
    return None


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

INTERVIEW_PROMPT_TEMPLATE = """\
You are helping the user author their refactoring taste file for continuous-refactoring.

Taste file target: {taste_path}
Taste settle target: {settle_path}
{existing_block}
Your job: interview the user with 6-8 focused questions. Probe concrete preferences on:
- error handling (translate, bubble, swallow)
- comments (when, when not)
- abstraction (wrappers, helpers, single-call abstractions)
- deletion vs preservation (compat code, fallbacks, legacy shims)
- naming (truthful names, rollout-shaped names)
- module boundaries (when to split, when to merge)
- tests (mocks, property vs example)
- anything else the user brings up

Rules:
- One question at a time. Wait for the answer before the next.
- Probe vague answers with follow-ups.
- Synthesize into 5-10 concise bullet points in the style: "- Do/Prefer X. Avoid Y when Z."
- Show the draft. Ask for corrections. Iterate until the user approves.
- Write the final bullet list to {taste_path}. Overwrite any existing content.
- After writing {taste_path}, compute its SHA-256 and write exactly
  'sha256:<hex>' to {settle_path}.
- After writing {settle_path}, do not modify either file again.
- Do not add a header -- the file is consumed verbatim.
- The host will end the session after both files settle.\
"""


TASTE_UPGRADE_PROMPT_TEMPLATE = """\
You are upgrading a refactoring taste file for continuous-refactoring.

Taste file target: {taste_path}
Taste settle target: {settle_path}

{version_context}

{existing_block}\
New dimensions to interview about:
- large-scope decisions: when to split vs. unify modules, when to introduce or
  remove interfaces, when cross-cutting concerns warrant a shared library vs.
  inline duplication.
- rollout style: caution level for wide-blast-radius changes, whether to
  feature-flag user-visible behavior, incremental steps vs. large-bang rewrites.

Rules:
- Ask 3-4 focused questions about the new dimensions only.
- One question at a time. Wait for the answer before the next.
- Probe vague answers with follow-ups.
- Preserve all existing taste preferences. Add new bullets for the new dimensions.
- The file MUST begin with the header line 'taste-scoping-version: {target_version}'
  followed by a blank line.
- Show the draft. Ask for corrections. Iterate until the user approves.
- Write the final content to {taste_path}. Overwrite any existing content.
- After writing {taste_path}, compute its SHA-256 and write exactly
  'sha256:<hex>' to {settle_path}.
- After writing {settle_path}, do not modify either file again.
- The host will end the session after both files settle.\
"""


def compose_taste_upgrade_prompt(
    taste_path: Path,
    settle_path: Path,
    existing_taste: str | None,
    stored_version: int | None,
    target_version: int,
) -> str:
    if stored_version is None:
        version_context = (
            "The stored taste has no version header. This is a legacy taste file.\n"
            "Replace it with a versioned v1 taste that includes the two new\n"
            "dimensions: large-scope decisions and rollout style."
        )
    else:
        version_context = (
            f"The stored taste is at version {stored_version}; "
            f"current is {target_version}."
        )
    if existing_taste:
        existing_block = (
            "Existing taste content (preserve existing preferences):\n\n"
            f"{existing_taste}\n\n"
        )
    else:
        existing_block = ""
    return TASTE_UPGRADE_PROMPT_TEMPLATE.format(
        taste_path=str(taste_path),
        settle_path=str(settle_path),
        version_context=version_context,
        existing_block=existing_block,
        target_version=target_version,
    )


def compose_interview_prompt(
    taste_path: Path,
    settle_path: Path,
    existing_taste: str | None,
) -> str:
    if existing_taste:
        existing_block = (
            "Existing taste content (treat as a starting draft, not a constraint):\n\n"
            f"{existing_taste}\n"
        )
    else:
        existing_block = ""
    return INTERVIEW_PROMPT_TEMPLATE.format(
        taste_path=str(taste_path),
        settle_path=str(settle_path),
        existing_block=existing_block,
    )


def prompt_file_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def compose_full_prompt(
    *,
    base_prompt: str,
    taste: str,
    target: Target,
    scope_instruction: str | None,
    validation_command: str,
    attempt: int,
    previous_failure: str | None = None,
    fix_amendment: str | None = None,
) -> str:
    sections: list[str] = [
        f"Attempt {attempt}",
        base_prompt,
        REQUIRED_PREAMBLE,
        f"## Refactoring Taste\n{taste}",
        _format_target_files(target.files),
        _first_scope(target.scoping, scope_instruction),
        f"## Validation\nRun: `{validation_command}`",
    ]
    if previous_failure:
        # previous_failure is summarize_output's tail (40 lines of validation command
        # or agent stdout+stderr). Verbatim input; trusted but not sanitized.
        sections.extend([
            "Previous attempt failed tests with this output:\n",
            previous_failure,
            "Use this as context only if it helps; do not copy test output into code.",
            "Only fix failures introduced by this refactoring pass.",
        ])
    if fix_amendment:
        sections.append(fix_amendment)
    return _join_sections(*sections)


PlanningStage = Literal[
    "approaches", "pick-best", "expand", "review", "final-review"
]

CLASSIFIER_PROMPT = """\
You are a refactoring classifier. Analyze the target and decide whether it can be
handled as a single cohesive cleanup batch or requires a multi-phase migration plan.

Decide needs-plan when:
- The change spans multiple module clusters with distinct rationales.
- Coordinated modifications cannot be validated atomically.
- Blast radius is large enough that incremental rollout reduces risk.

Decide cohesive-cleanup when:
- The change fits in one session with one rationale and one validation path.
- All modifications share the same module cluster and can be validated together.

Refactoring taste is injected by the caller. Respect it when evaluating scope
and risk thresholds.

## Output Contract
Your final line MUST be exactly one of:
  decision: cohesive-cleanup \u2014 <short reason>
  decision: needs-plan \u2014 <short reason>\
"""

PLANNING_APPROACHES_PROMPT = """\
You are a planning agent generating candidate approaches for a refactoring migration.

Analyze the codebase and produce 2\u20134 distinct approach files. Each approach should
outline a strategy, its tradeoffs, estimated phases, and risk profile.

Write each approach to approaches/<idea>.md where <idea> is a short descriptive slug.

Refactoring taste is injected by the caller. Respect it when designing approaches
and evaluating tradeoffs.\
"""

PLANNING_PICK_BEST_PROMPT = """\
You are a planning agent selecting the best approach for a refactoring migration.

Review the candidate approaches in approaches/<idea>.md. Select the approach with
the best balance of risk, clarity, and incremental verifiability.

State your choice and rationale. The chosen approach will be expanded into plan.md
and phase-<n>-<name>.md files.

Refactoring taste is injected by the caller. Use it to break ties between
comparable approaches.\
"""

PLANNING_EXPAND_PROMPT = """\
You are a planning agent expanding the chosen approach into a detailed migration plan.

Read the chosen approach from approaches/<idea>.md and produce:
1. plan.md \u2014 the full migration plan with numbered phases, dependencies, and
   validation strategy.
2. phase-<n>-<name>.md for each phase \u2014 detailed instructions, scope, ready_when
   conditions, and validation steps.

Each phase must be independently verifiable. Order phases so earlier ones reduce
risk for later ones. Every phase must leave the repository shippable.

Refactoring taste is injected by the caller. Respect it when scoping phases
and defining quality bars.\
"""

PLANNING_REVIEW_PROMPT = """\
You are a planning reviewer examining a refactoring migration plan.

Review plan.md, each phase-<n>-<name>.md file, and the approaches in
approaches/<idea>.md for context. Check:
- Each phase is independently verifiable and leaves the repo shippable.
- Phase ordering minimizes risk and respects dependencies.
- No phase requires product or architecture judgment beyond the taste.
- Ready-when conditions are concrete and mechanically checkable.
- The plan does not modify source files outside the migration scope.

List findings as numbered items. If no findings, state "no findings."

Refactoring taste is injected by the caller. Verify the plan respects it.\
"""

PLANNING_FINAL_REVIEW_PROMPT = """\
You are performing the final gate review of a refactoring migration plan.

The plan has been through at least one review-revise cycle. Assess:
- Is the plan safe to execute automatically without human judgment?
- Does it require human review at any decision point?
- Is it fundamentally flawed and should be rejected?

Review plan.md, phase-<n>-<name>.md files, and approaches/<idea>.md.

Refactoring taste is injected by the caller. Use it as the quality bar.

## Output Contract
Your final line MUST be exactly one of:
  final-decision: approve-auto \u2014 <short reason>
  final-decision: approve-needs-human \u2014 <short reason>
  final-decision: reject \u2014 <short reason>\
"""

PHASE_READY_CHECK_PROMPT = """\
You are checking whether a migration phase is ready to execute.

Assess:
- Is the ready_when condition for this phase currently met?
- Are prerequisites from earlier phases actually complete?
- Is the working tree in a state where this phase can safely execute?

Refactoring taste is injected by the caller. Respect it when assessing readiness.

## Output Contract
Your final line MUST be exactly one of:
  ready: yes
  ready: no \u2014 <reason>
  ready: unverifiable \u2014 <reason>\
"""

PHASE_EXECUTION_PROMPT = """\
You are executing a single phase of a refactoring migration.

Execute the work described in the phase file. Follow the plan exactly.
All changes must keep the project in a state where all tests pass.
Do not modify files outside the scope defined in the phase plan.

Refactoring taste is injected by the caller. Respect it in all code changes.\
"""

_PLANNING_STAGE_PROMPTS: dict[str, str] = {
    "approaches": PLANNING_APPROACHES_PROMPT,
    "pick-best": PLANNING_PICK_BEST_PROMPT,
    "expand": PLANNING_EXPAND_PROMPT,
    "review": PLANNING_REVIEW_PROMPT,
    "final-review": PLANNING_FINAL_REVIEW_PROMPT,
}


def _format_manifest_summary(manifest: MigrationManifest) -> str:
    phases = "\n".join(
        f"  {i}. {p.name} ({'done' if p.done else 'pending'}) \u2014 {p.ready_when}"
        for i, p in enumerate(manifest.phases)
    )
    return (
        f"Name: {manifest.name}\n"
        f"Status: {manifest.status}\n"
        f"Current phase: {manifest.current_phase}\n"
        f"Phases:\n{phases}"
    )


def compose_classifier_prompt(target: Target, taste: str) -> str:
    return _join_sections(
        CLASSIFIER_PROMPT,
        f"## Target\n{target.description}",
        _format_target_files(target.files),
        _first_scope(target.scoping),
        f"## Taste\n{taste}",
    )


def compose_planning_prompt(
    stage: PlanningStage,
    migration_name: str,
    taste: str,
    context: str,
) -> str:
    base = _PLANNING_STAGE_PROMPTS[stage]
    return _join_sections(
        base,
        f"## Migration\n{migration_name}",
        f"## Context\n{context}" if context else None,
        f"## Taste\n{taste}",
    )


def compose_phase_ready_prompt(
    phase: PhaseSpec, manifest: MigrationManifest,
) -> str:
    return _join_sections(
        PHASE_READY_CHECK_PROMPT,
        f"## Phase\nName: {phase.name}\nFile: {phase.file}\nReady when: {phase.ready_when}",
        f"## Manifest\n{_format_manifest_summary(manifest)}",
    )


def compose_phase_execution_prompt(
    phase: PhaseSpec, manifest: MigrationManifest, taste: str,
) -> str:
    return _join_sections(
        PHASE_EXECUTION_PROMPT,
        f"## Phase\nName: {phase.name}\nFile: {phase.file}",
        f"## Manifest\n{_format_manifest_summary(manifest)}",
        f"## Taste\n{taste}",
    )


REVIEW_PERFORM_PROMPT = """\
You are conducting a human review of a refactoring migration that was flagged
for human input during planning.

Your job:
1. Read the migration plan (plan.md), the current phase file, and the manifest.
2. Present the situation to the user: what the migration does, what phase it is
   on, and why it was flagged for review.
3. Ask the user whatever questions are needed to unblock the migration.
4. Based on the user's answers, update plan.md and/or phase files as needed.
5. When the review is complete and the user approves, update manifest.json:
   set "awaiting_human_review" to false.

If the user wants to abort or cannot resolve the review, leave
awaiting_human_review as true and exit cleanly.

## Output Contract
When the review is successfully completed:
- manifest.json MUST have "awaiting_human_review": false
- Any plan or phase file updates MUST be written before exiting\
"""


def compose_review_perform_prompt(
    migration_name: str,
    manifest_path: Path,
    plan_path: Path,
    phase_file: str | None,
    manifest: MigrationManifest,
) -> str:
    sections: list[str] = [
        REVIEW_PERFORM_PROMPT,
        f"## Migration\nName: {migration_name}",
        f"## Manifest\nPath: {manifest_path}\n{_format_manifest_summary(manifest)}",
        f"## Plan\nPath: {plan_path}",
    ]
    if phase_file:
        sections.append(f"## Current Phase File\n{phase_file}")
    return _join_sections(*sections)
