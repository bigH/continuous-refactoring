from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeGuard, cast, get_args

from continuous_refactoring.artifacts import ContinuousRefactorError, iso_timestamp

__all__ = [
    "CompletedPlanningStep",
    "FeedbackSource",
    "FinalPlanningDecision",
    "PlanningCursor",
    "PlanningState",
    "PlanningStep",
    "PlanningStepOutcome",
    "UserPlanningFeedback",
    "append_planning_feedback",
    "complete_planning_step",
    "initial_planning_state",
    "is_executable_planning_step",
    "load_planning_state",
    "new_planning_state",
    "planning_stage_stdout_path",
    "planning_state_path",
    "planning_step_stdout",
    "reopen_planning_for_revise",
    "replay_planning_state",
    "save_planning_state",
    "validate_planning_state",
    "write_planning_stage_stdout",
]

SCHEMA_VERSION = 1

PlanningStep = Literal[
    "approaches",
    "pick-best",
    "expand",
    "review",
    "revise",
    "review-2",
    "final-review",
]
TerminalPlanningCursor = Literal[
    "terminal-ready",
    "terminal-ready-awaiting-human",
    "terminal-skipped",
]
PlanningCursor = PlanningStep | TerminalPlanningCursor
FinalPlanningDecision = Literal["approve-auto", "approve-needs-human", "reject"]
PlanningStepOutcome = Literal[
    "completed",
    "clear",
    "findings",
    "approve-auto",
    "approve-needs-human",
    "reject",
]
FeedbackSource = Literal["message", "file"]

_PLANNING_STEPS: tuple[str, ...] = cast(tuple[str, ...], get_args(PlanningStep))
_TERMINAL_CURSORS: tuple[str, ...] = cast(
    tuple[str, ...], get_args(TerminalPlanningCursor)
)
_PLANNING_CURSORS: tuple[str, ...] = (*_PLANNING_STEPS, *_TERMINAL_CURSORS)
_FINAL_DECISIONS: tuple[str, ...] = cast(
    tuple[str, ...], get_args(FinalPlanningDecision)
)
_STEP_OUTCOMES: tuple[str, ...] = cast(tuple[str, ...], get_args(PlanningStepOutcome))

_COMPLETED_OUTCOME = "completed"
_TERMINAL_BY_DECISION: dict[str, TerminalPlanningCursor] = {
    "approve-auto": "terminal-ready",
    "approve-needs-human": "terminal-ready-awaiting-human",
    "reject": "terminal-skipped",
}


@dataclass(frozen=True)
class CompletedPlanningStep:
    name: PlanningStep
    completed_at: str
    outcome: PlanningStepOutcome
    outputs: dict[str, str]
    agent: str | None = None
    model: str | None = None
    effort: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name,
            "completed_at": self.completed_at,
            "outcome": self.outcome,
            "outputs": dict(self.outputs),
        }
        if self.agent is not None:
            payload["agent"] = self.agent
        if self.model is not None:
            payload["model"] = self.model
        if self.effort is not None:
            payload["effort"] = self.effort
        return payload


@dataclass(frozen=True)
class UserPlanningFeedback:
    received_at: str
    source: FeedbackSource
    text: str

    def to_payload(self) -> dict[str, object]:
        return {
            "received_at": self.received_at,
            "source": self.source,
            "text": self.text,
        }


@dataclass(frozen=True)
class PlanningState:
    schema_version: int
    target: str
    next_step: PlanningCursor
    completed_steps: tuple[CompletedPlanningStep, ...]
    started_at: str
    updated_at: str
    feedback: tuple[UserPlanningFeedback, ...]
    review_findings: str | None
    final_decision: FinalPlanningDecision | None
    final_reason: str | None
    revision_base_step_counts: tuple[int, ...] = ()

    @property
    def revision_base_step_count(self) -> int | None:
        if not self.revision_base_step_counts:
            return None
        return self.revision_base_step_counts[-1]


@dataclass(frozen=True)
class _ReplayResult:
    next_step: PlanningCursor
    review_findings: str | None
    final_decision: FinalPlanningDecision | None


def planning_state_path(mig_root: Path) -> Path:
    return mig_root / ".planning" / "state.json"


def planning_stage_stdout_path(mig_root: Path, step: str) -> Path:
    _require_step(step)
    return mig_root / ".planning" / "stages" / f"{step}.stdout.md"


def new_planning_state(target: str, *, now: str | None = None) -> PlanningState:
    timestamp = now or iso_timestamp()
    return PlanningState(
        schema_version=SCHEMA_VERSION,
        target=target,
        next_step="approaches",
        completed_steps=(),
        started_at=timestamp,
        updated_at=timestamp,
        feedback=(),
        review_findings=None,
        final_decision=None,
        final_reason=None,
        revision_base_step_counts=(),
    )


def initial_planning_state(target: str, *, now: str | None = None) -> PlanningState:
    return new_planning_state(target, now=now)


def is_executable_planning_step(value: object) -> TypeGuard[PlanningStep]:
    return isinstance(value, str) and value in _PLANNING_STEPS


def complete_planning_step(
    state: PlanningState,
    step: str,
    outcome: str,
    outputs: dict[str, str],
    *,
    completed_at: str | None = None,
    agent: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    final_reason: str | None = None,
) -> PlanningState:
    step_name = _require_step(step)
    step_outcome = _require_outcome(outcome)
    replay = _replay_details(state)
    if state.next_step != replay.next_step:
        raise ContinuousRefactorError(
            f"Planning state next_step {state.next_step!r} does not match "
            f"replayed cursor {replay.next_step!r}"
        )
    _validate_replay_metadata(state, replay)
    if state.next_step != step_name:
        raise ContinuousRefactorError(
            f"Cannot complete planning step {step_name!r}; "
            f"current step is {state.next_step!r}"
        )
    completed = CompletedPlanningStep(
        name=step_name,
        completed_at=completed_at or iso_timestamp(),
        outcome=step_outcome,
        outputs=dict(outputs),
        agent=agent,
        model=model,
        effort=effort,
    )
    _validate_output_refs_syntax(completed)
    updated_steps = (*state.completed_steps, completed)
    updated = PlanningState(
        schema_version=state.schema_version,
        target=state.target,
        next_step=state.next_step,
        completed_steps=updated_steps,
        started_at=state.started_at,
        updated_at=completed.completed_at,
        feedback=state.feedback,
        review_findings=state.review_findings,
        final_decision=state.final_decision,
        final_reason=state.final_reason,
        revision_base_step_counts=state.revision_base_step_counts,
    )
    replay = _replay_details(updated)
    return PlanningState(
        schema_version=updated.schema_version,
        target=updated.target,
        next_step=replay.next_step,
        completed_steps=updated.completed_steps,
        started_at=updated.started_at,
        updated_at=updated.updated_at,
        feedback=updated.feedback,
        review_findings=replay.review_findings,
        final_decision=replay.final_decision,
        final_reason=_next_final_reason(
            state.final_reason,
            replay.final_decision,
            final_reason,
        ),
        revision_base_step_counts=updated.revision_base_step_counts,
    )


def append_planning_feedback(
    state: PlanningState,
    text: str,
    source: FeedbackSource,
    *,
    now: str | None = None,
) -> PlanningState:
    feedback_source = _require_feedback_source(source, field="source")
    feedback = UserPlanningFeedback(
        received_at=now or iso_timestamp(),
        source=feedback_source,
        text=text,
    )
    updated = PlanningState(
        schema_version=state.schema_version,
        target=state.target,
        next_step=state.next_step,
        completed_steps=state.completed_steps,
        started_at=state.started_at,
        updated_at=feedback.received_at,
        feedback=(*state.feedback, feedback),
        review_findings=state.review_findings,
        final_decision=state.final_decision,
        final_reason=state.final_reason,
        revision_base_step_counts=state.revision_base_step_counts,
    )
    _validate_replay_metadata(updated, _replay_details(updated))
    return updated


def reopen_planning_for_revise(
    state: PlanningState,
    *,
    now: str | None = None,
) -> PlanningState:
    replay = _replay_details(state)
    if replay.next_step not in ("terminal-ready", "terminal-ready-awaiting-human"):
        raise ContinuousRefactorError(
            f"Cannot reopen planning state at {replay.next_step!r} for revise"
        )
    updated = PlanningState(
        schema_version=state.schema_version,
        target=state.target,
        next_step="revise",
        completed_steps=state.completed_steps,
        started_at=state.started_at,
        updated_at=now or iso_timestamp(),
        feedback=state.feedback,
        review_findings=None,
        final_decision=None,
        final_reason=None,
        revision_base_step_counts=(
            *state.revision_base_step_counts,
            len(state.completed_steps),
        ),
    )
    _validate_replay_metadata(updated, _replay_details(updated))
    return updated


def replay_planning_state(state: PlanningState) -> PlanningCursor:
    return _replay_details(state).next_step


def validate_planning_state(
    state: PlanningState,
    repo_root: Path,
    *,
    state_path: Path | None = None,
    published_migration_root: Path | None = None,
) -> None:
    if state.schema_version != SCHEMA_VERSION:
        raise ContinuousRefactorError(
            f"Unsupported planning state schema_version: {state.schema_version!r}"
        )
    replay = _replay_details(state)
    if state.next_step != replay.next_step:
        raise ContinuousRefactorError(
            f"Planning state next_step {state.next_step!r} does not match "
            f"replayed cursor {replay.next_step!r}"
        )
    _validate_replay_metadata(state, replay)
    migration_root = state_path.parent.parent if state_path is not None else None
    _validate_output_paths(
        state,
        repo_root,
        migration_root,
        published_migration_root=published_migration_root,
    )


def _validate_replay_metadata(state: PlanningState, replay: _ReplayResult) -> None:
    if state.review_findings != replay.review_findings:
        raise ContinuousRefactorError(
            "Planning state review_findings does not match replayed history"
        )
    if state.final_decision != replay.final_decision:
        raise ContinuousRefactorError(
            "Planning state final_decision does not match replayed history"
        )
    if replay.final_decision is None and state.final_reason is not None:
        raise ContinuousRefactorError(
            "Planning state final_reason requires a final-review decision"
        )
    if replay.final_decision is not None and not state.final_reason:
        raise ContinuousRefactorError(
            "Planning state terminal final-review requires final_reason"
        )


def load_planning_state(
    repo_root: Path,
    path: Path,
    *,
    published_migration_root: Path | None = None,
) -> PlanningState:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ContinuousRefactorError(
            f"Could not load planning state {path}: {error}"
        ) from error
    try:
        raw = json.loads(content)
    except json.JSONDecodeError as error:
        raise ContinuousRefactorError(
            f"Could not parse planning state {path}: {error}"
        ) from error
    state = _decode_state_payload(raw)
    validate_planning_state(
        state,
        repo_root,
        state_path=path,
        published_migration_root=published_migration_root,
    )
    return state


def save_planning_state(
    state: PlanningState,
    path: Path,
    *,
    repo_root: Path,
    published_migration_root: Path | None = None,
) -> None:
    validate_planning_state(
        state,
        repo_root,
        state_path=path,
        published_migration_root=published_migration_root,
    )
    content = _encode_state_payload(state)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ContinuousRefactorError(
            f"Could not save planning state {path}: {error}"
        ) from error

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
        ) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(content)
    except OSError as error:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        raise ContinuousRefactorError(
            f"Could not save planning state {path}: {error}"
        ) from error

    try:
        tmp_path.replace(path)
    except OSError as error:
        tmp_path.unlink(missing_ok=True)
        raise ContinuousRefactorError(
            f"Could not save planning state {path}: {error}"
        ) from error


def write_planning_stage_stdout(
    repo_root: Path,
    mig_root: Path,
    step: str,
    stdout: str,
    *,
    published_migration_root: Path | None = None,
) -> dict[str, str]:
    path = _next_planning_stage_stdout_path(mig_root, step)
    _write_text_atomic(path, stdout)
    if published_migration_root is None:
        ref_path = path
    else:
        ref_path = published_migration_root / path.relative_to(mig_root)
    return {"stdout": _repo_relative(ref_path, repo_root)}


def planning_step_stdout(
    state: PlanningState,
    repo_root: Path,
    step: str,
    *,
    state_path: Path,
    published_migration_root: Path | None = None,
) -> tuple[str, str]:
    validate_planning_state(
        state,
        repo_root,
        state_path=state_path,
        published_migration_root=published_migration_root,
    )
    step_name = _require_step(step)
    migration_root = state_path.parent.parent
    for completed in reversed(state.completed_steps):
        if completed.name != step_name:
            continue
        stdout_ref = completed.outputs.get("stdout")
        if stdout_ref is None:
            break
        path = _output_path_for_ref(
            stdout_ref,
            repo_root,
            migration_root,
            published_migration_root=published_migration_root,
        )
        try:
            return stdout_ref, path.read_text(encoding="utf-8")
        except OSError as error:
            raise ContinuousRefactorError(
                f"Could not read planning output {stdout_ref}: {error}"
            ) from error
    raise ContinuousRefactorError(
        f"Planning state has no accepted stdout output for step {step_name!r}"
    )


def _next_planning_stage_stdout_path(mig_root: Path, step: str) -> Path:
    base = planning_stage_stdout_path(mig_root, step)
    if not base.exists():
        return base
    index = 2
    while True:
        candidate = base.with_name(f"{step}-{index}.stdout.md")
        if not candidate.exists():
            return candidate
        index += 1


def _replay_details(state: PlanningState) -> _ReplayResult:
    expected: PlanningCursor = "approaches"
    review_findings: str | None = None
    final_decision: FinalPlanningDecision | None = None

    _validate_revision_base_step_counts(state)
    revision_anchor_index = 0
    revision_anchors = state.revision_base_step_counts
    for index, completed in enumerate(state.completed_steps):
        if (
            revision_anchor_index < len(revision_anchors)
            and revision_anchors[revision_anchor_index] == index
        ):
            expected, review_findings, final_decision = _reopen_cursor(expected)
            revision_anchor_index += 1
        if expected not in _PLANNING_STEPS:
            raise ContinuousRefactorError(
                f"Planning step {completed.name!r} appears after terminal cursor {expected!r}"
            )
        if completed.name != expected:
            raise ContinuousRefactorError(
                f"Completed planning step {completed.name!r} is invalid: "
                f"expected {expected}"
            )
        expected, review_findings, final_decision = _advance_cursor(
            completed,
            review_findings=review_findings,
            final_decision=final_decision,
        )

    if (
        revision_anchor_index < len(revision_anchors)
        and revision_anchors[revision_anchor_index] == len(state.completed_steps)
    ):
        expected, review_findings, final_decision = _reopen_cursor(expected)
        revision_anchor_index += 1

    return _ReplayResult(
        next_step=expected,
        review_findings=review_findings,
        final_decision=final_decision,
    )


def _validate_revision_base_step_counts(state: PlanningState) -> None:
    previous = 0
    for value in state.revision_base_step_counts:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ContinuousRefactorError(
                "Planning state revision_base_step_counts must contain integers"
            )
        if value < 1 or value > len(state.completed_steps):
            raise ContinuousRefactorError(
                "Planning state revision_base_step_counts is outside completed history"
            )
        if value <= previous:
            raise ContinuousRefactorError(
                "Planning state revision_base_step_counts must be strictly increasing"
            )
        previous = value


def _reopen_cursor(
    cursor: PlanningCursor,
) -> tuple[PlanningCursor, str | None, FinalPlanningDecision | None]:
    if cursor not in ("terminal-ready", "terminal-ready-awaiting-human"):
        raise ContinuousRefactorError(
            "Planning state revision_base_step_counts must point at a "
            f"terminal ready cursor, got {cursor!r}"
        )
    return "revise", None, None


def _advance_cursor(
    completed: CompletedPlanningStep,
    *,
    review_findings: str | None,
    final_decision: FinalPlanningDecision | None,
) -> tuple[PlanningCursor, str | None, FinalPlanningDecision | None]:
    _require_valid_outcome_for_step(completed)
    if completed.name == "approaches":
        return "pick-best", review_findings, final_decision
    if completed.name == "pick-best":
        return "expand", review_findings, final_decision
    if completed.name == "expand":
        return "review", review_findings, final_decision
    if completed.name == "review":
        if completed.outcome == "findings":
            return "revise", _required_stdout_output(completed), final_decision
        return "final-review", review_findings, final_decision
    if completed.name == "revise":
        return "review-2", review_findings, final_decision
    if completed.name == "review-2":
        return "final-review", review_findings, final_decision
    decision = cast(FinalPlanningDecision, completed.outcome)
    return _TERMINAL_BY_DECISION[decision], review_findings, decision


def _require_valid_outcome_for_step(completed: CompletedPlanningStep) -> None:
    allowed = _allowed_outcomes(completed.name)
    if completed.outcome not in allowed:
        allowed_text = ", ".join(repr(outcome) for outcome in allowed)
        raise ContinuousRefactorError(
            f"Planning step {completed.name!r} outcome {completed.outcome!r} "
            f"is invalid; expected one of {allowed_text}"
        )


def _allowed_outcomes(step: PlanningStep) -> tuple[str, ...]:
    if step in ("approaches", "pick-best", "expand", "revise"):
        return (_COMPLETED_OUTCOME,)
    if step == "review":
        return ("clear", "findings")
    if step == "review-2":
        return ("clear",)
    return _FINAL_DECISIONS


def _required_stdout_output(completed: CompletedPlanningStep) -> str:
    stdout_ref = completed.outputs.get("stdout")
    if not stdout_ref:
        raise ContinuousRefactorError(
            f"Planning step {completed.name!r} must record a stdout output"
        )
    return stdout_ref


def _next_final_reason(
    previous: str | None,
    final_decision: FinalPlanningDecision | None,
    final_reason: str | None,
) -> str | None:
    if final_decision is None:
        return None
    if final_reason is not None:
        return final_reason
    return previous


def _validate_output_paths(
    state: PlanningState,
    repo_root: Path,
    migration_root: Path | None,
    *,
    published_migration_root: Path | None,
) -> None:
    for completed in state.completed_steps:
        stdout_ref = _required_stdout_output(completed)
        _validate_output_refs_syntax(completed)
        _require_existing_output(
            stdout_ref,
            repo_root,
            migration_root,
            published_migration_root=published_migration_root,
            field=f"completed_steps.{completed.name}.outputs.stdout",
        )


def _validate_output_refs_syntax(completed: CompletedPlanningStep) -> None:
    if completed.outputs.keys() != {"stdout"}:
        raise ContinuousRefactorError(
            f"Planning step {completed.name!r} has unsupported outputs"
        )
    _require_repo_relative_path(
        _required_stdout_output(completed),
        field=f"completed_steps.{completed.name}.outputs.stdout",
    )


def _require_existing_output(
    value: str,
    repo_root: Path,
    migration_root: Path | None,
    *,
    published_migration_root: Path | None,
    field: str,
) -> None:
    ref = _require_repo_relative_path(value, field=field)
    repo_output_path = repo_root / ref
    output_path = _output_path_for_ref(
        value,
        repo_root,
        migration_root,
        published_migration_root=published_migration_root,
    )
    resolved_output = output_path.resolve()
    try:
        repo_output_path.resolve().relative_to(repo_root.resolve())
    except ValueError as error:
        raise ContinuousRefactorError(
            f"Planning output path {value!r} must be repo-relative"
        ) from error
    if published_migration_root is not None:
        try:
            repo_output_path.resolve().relative_to(published_migration_root.resolve())
        except ValueError as error:
            raise ContinuousRefactorError(
                f"Planning output path {value!r} must stay inside the published migration directory"
            ) from error
    if migration_root is not None:
        try:
            resolved_output.relative_to(migration_root.resolve())
        except ValueError as error:
            raise ContinuousRefactorError(
                f"Planning output path {value!r} must stay inside the migration directory"
            ) from error
    if output_path.is_symlink():
        raise ContinuousRefactorError(
            f"Planning output path {value!r} must be a regular file, not a symlink"
        )
    if not output_path.is_file():
        raise ContinuousRefactorError(f"missing planning output: {value}")


def _output_path_for_ref(
    value: str,
    repo_root: Path,
    migration_root: Path | None,
    *,
    published_migration_root: Path | None,
) -> Path:
    ref_path = repo_root / _require_repo_relative_path(value, field="stdout")
    if migration_root is None or published_migration_root is None:
        return ref_path
    try:
        relative = ref_path.resolve().relative_to(published_migration_root.resolve())
    except ValueError:
        return ref_path
    return migration_root / relative


def _require_repo_relative_path(value: str, *, field: str) -> Path:
    if not isinstance(value, str):
        raise ContinuousRefactorError(f"Planning field {field!r} must be a string")
    ref = Path(value)
    if str(ref) in ("", ".") or ref.is_absolute() or ".." in ref.parts:
        raise ContinuousRefactorError(
            f"Planning output path {value!r} must be repo-relative"
        )
    return ref


def _repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError as error:
        raise ContinuousRefactorError(
            f"Planning output path {path} must be inside repository {repo_root}"
        ) from error


def _decode_state_payload(raw_payload: object) -> PlanningState:
    raw = _require_mapping(raw_payload, field="planning state")
    _require_keys(
        raw,
        {
            "schema_version",
            "target",
            "next_step",
            "completed_steps",
            "started_at",
            "updated_at",
            "feedback",
            "review_findings",
            "final_decision",
            "final_reason",
        },
        optional={"revision_base_step_count", "revision_base_step_counts"},
        field="planning state",
    )
    revision_base_step_counts = _decode_revision_base_step_counts(raw)
    return PlanningState(
        schema_version=_require_int(raw.get("schema_version"), field="schema_version"),
        target=_require_str(raw.get("target"), field="target"),
        next_step=_require_cursor(raw.get("next_step"), field="next_step"),
        completed_steps=_require_completed_steps(raw.get("completed_steps")),
        started_at=_require_str(raw.get("started_at"), field="started_at"),
        updated_at=_require_str(raw.get("updated_at"), field="updated_at"),
        feedback=_require_feedback_tuple(raw.get("feedback"), field="feedback"),
        review_findings=_optional_str(raw.get("review_findings"), field="review_findings"),
        final_decision=_optional_final_decision(
            raw.get("final_decision"), field="final_decision"
        ),
        final_reason=_optional_str(raw.get("final_reason"), field="final_reason"),
        revision_base_step_counts=revision_base_step_counts,
    )


def _encode_state_payload(state: PlanningState) -> str:
    replay = _replay_details(state)
    if state.next_step != replay.next_step:
        raise ContinuousRefactorError(
            f"Cannot save planning state with next_step {state.next_step!r}; "
            f"replayed cursor is {replay.next_step!r}"
        )
    _validate_replay_metadata(state, replay)
    payload = {
        "schema_version": state.schema_version,
        "target": state.target,
        "next_step": state.next_step,
        "completed_steps": [step.to_payload() for step in state.completed_steps],
        "started_at": state.started_at,
        "updated_at": state.updated_at,
        "feedback": [feedback.to_payload() for feedback in state.feedback],
        "review_findings": state.review_findings,
        "final_decision": state.final_decision,
        "final_reason": state.final_reason,
        "revision_base_step_counts": list(state.revision_base_step_counts),
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _decode_revision_base_step_counts(
    raw: dict[str, object],
) -> tuple[int, ...]:
    if "revision_base_step_counts" in raw:
        if "revision_base_step_count" in raw and raw["revision_base_step_count"] is not None:
            raise ContinuousRefactorError(
                "Planning state may not mix revision_base_step_count and "
                "revision_base_step_counts"
            )
        return _require_int_tuple(
            raw.get("revision_base_step_counts"),
            field="revision_base_step_counts",
        )
    legacy_value = _optional_int(
        raw.get("revision_base_step_count"),
        field="revision_base_step_count",
    )
    if legacy_value is None:
        return ()
    return (legacy_value,)


def _require_completed_steps(value: object) -> tuple[CompletedPlanningStep, ...]:
    if not isinstance(value, list):
        raise ContinuousRefactorError(
            f"Planning field 'completed_steps' must be a list: {value!r}"
        )
    return tuple(
        _require_completed_step(raw_step, index=index)
        for index, raw_step in enumerate(value)
    )


def _require_completed_step(raw_step: object, *, index: int) -> CompletedPlanningStep:
    raw = _require_mapping(raw_step, field=f"completed_steps[{index}]")
    _require_keys(
        raw,
        {"name", "completed_at", "outcome", "outputs"},
        optional={"agent", "model", "effort"},
        field=f"completed_steps[{index}]",
    )
    return CompletedPlanningStep(
        name=_require_step(raw.get("name")),
        completed_at=_require_str(
            raw.get("completed_at"), field=f"completed_steps[{index}].completed_at"
        ),
        outcome=_require_outcome(raw.get("outcome")),
        outputs=_require_outputs(raw.get("outputs"), index=index),
        agent=_optional_str(raw.get("agent"), field=f"completed_steps[{index}].agent"),
        model=_optional_str(raw.get("model"), field=f"completed_steps[{index}].model"),
        effort=_optional_str(raw.get("effort"), field=f"completed_steps[{index}].effort"),
    )


def _require_outputs(value: object, *, index: int) -> dict[str, str]:
    raw = _require_mapping(value, field=f"completed_steps[{index}].outputs")
    outputs: dict[str, str] = {}
    for key, output in raw.items():
        if not isinstance(key, str):
            raise ContinuousRefactorError(
                f"Planning outputs keys must be strings: {key!r}"
            )
        outputs[key] = _require_str(
            output,
            field=f"completed_steps[{index}].outputs.{key}",
        )
    return outputs


def _require_mapping(value: object, *, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ContinuousRefactorError(
            f"Planning field {field!r} must be an object: {value!r}"
        )
    return value


def _require_keys(
    raw: dict[str, object],
    required: set[str],
    *,
    field: str,
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    missing = sorted(required - raw.keys())
    extra = sorted(raw.keys() - allowed)
    if missing:
        raise ContinuousRefactorError(
            f"Planning field {field!r} is missing keys: {', '.join(missing)}"
        )
    if extra:
        raise ContinuousRefactorError(
            f"Planning field {field!r} has unknown keys: {', '.join(extra)}"
        )


def _require_str(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ContinuousRefactorError(
            f"Planning field {field!r} must be a string: {value!r}"
        )
    return value


def _optional_str(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    return _require_str(value, field=field)


def _require_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContinuousRefactorError(
            f"Planning field {field!r} must be an integer: {value!r}"
        )
    return value


def _optional_int(value: object, *, field: str) -> int | None:
    if value is None:
        return None
    return _require_int(value, field=field)


def _require_int_tuple(value: object, *, field: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise ContinuousRefactorError(
            f"Planning field {field!r} must be a list: {value!r}"
        )
    return tuple(
        _require_int(item, field=f"{field}[{index}]")
        for index, item in enumerate(value)
    )


def _require_feedback_tuple(
    value: object,
    *,
    field: str,
) -> tuple[UserPlanningFeedback, ...]:
    if not isinstance(value, list):
        raise ContinuousRefactorError(
            f"Planning field {field!r} must be a list: {value!r}"
        )
    return tuple(
        _require_feedback(item, field=f"{field}[{index}]")
        for index, item in enumerate(value)
    )


def _require_feedback(value: object, *, field: str) -> UserPlanningFeedback:
    if isinstance(value, str):
        return UserPlanningFeedback(received_at="", source="message", text=value)
    raw = _require_mapping(value, field=field)
    _require_keys(raw, {"received_at", "source", "text"}, field=field)
    return UserPlanningFeedback(
        received_at=_require_str(raw.get("received_at"), field=f"{field}.received_at"),
        source=_require_feedback_source(raw.get("source"), field=f"{field}.source"),
        text=_require_str(raw.get("text"), field=f"{field}.text"),
    )


def _require_feedback_source(value: object, *, field: str) -> FeedbackSource:
    source = _require_str(value, field=field)
    if source not in ("message", "file"):
        raise ContinuousRefactorError(
            f"Planning field {field!r} must be 'message' or 'file': {source!r}"
        )
    return cast(FeedbackSource, source)


def _require_cursor(value: object, *, field: str) -> PlanningCursor:
    if not isinstance(value, str):
        raise ContinuousRefactorError(
            f"Planning field {field!r} must be a string: {value!r}"
        )
    if value not in _PLANNING_CURSORS:
        raise ContinuousRefactorError(f"Unknown planning cursor: {value!r}")
    return cast(PlanningCursor, value)


def _require_step(value: object) -> PlanningStep:
    if not isinstance(value, str):
        raise ContinuousRefactorError(
            f"Planning step name must be a string: {value!r}"
        )
    if value not in _PLANNING_STEPS:
        raise ContinuousRefactorError(f"Unknown planning step: {value!r}")
    return cast(PlanningStep, value)


def _require_outcome(value: object) -> PlanningStepOutcome:
    if not isinstance(value, str):
        raise ContinuousRefactorError(
            f"Planning step outcome must be a string: {value!r}"
        )
    if value not in _STEP_OUTCOMES:
        raise ContinuousRefactorError(f"Unknown planning outcome: {value!r}")
    return cast(PlanningStepOutcome, value)


def _optional_final_decision(
    value: object,
    *,
    field: str,
) -> FinalPlanningDecision | None:
    if value is None:
        return None
    decision = _require_str(value, field=field)
    if decision not in _FINAL_DECISIONS:
        raise ContinuousRefactorError(f"Unknown final planning decision: {decision!r}")
    return cast(FinalPlanningDecision, decision)


def _write_text_atomic(path: Path, content: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ContinuousRefactorError(
            f"Could not save planning output {path}: {error}"
        ) from error

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
        ) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(content)
    except OSError as error:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        raise ContinuousRefactorError(
            f"Could not save planning output {path}: {error}"
        ) from error

    try:
        tmp_path.replace(path)
    except OSError as error:
        tmp_path.unlink(missing_ok=True)
        raise ContinuousRefactorError(
            f"Could not save planning output {path}: {error}"
        ) from error
