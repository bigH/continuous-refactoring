# Approach: Minimal Slim — Extract Status Parsing and Failure Reporting

## Summary

Conservative pass: pull out the two cleanest seams and leave routing +
orchestration alone. Move `AgentStatus` / status parsing / text
sanitation to `decisions.py`, and the reason-for-failure document
writer to `failure_report.py`. Stop there.

## Target Shape

- `decisions.py` — `AgentStatus`, `RunnerDecision`, `RetryRecommendation`,
  `RouteOutcome`, `DecisionRecord`, `_parse_agent_status_block`,
  `_read_agent_status`, `_status_path_text`, `_sanitize_text`,
  `_status_summary`, `_resolved_phase_reached`, `_error_failure_kind`,
  `_default_retry_recommendation`.
- `failure_report.py` — `_write_reason_for_failure`, `_next_step_text`,
  `_yaml_scalar`, `_persist_decision`, `_effective_record`,
  `_relative_path`, `_retry_context`.
- `loop.py` retains routing, `_run_refactor_attempt`, `run_once`,
  `run_loop`. Shrinks to ~1100 lines.

## Phases

1. Extract `decisions.py`. Validation: full tests.
2. Extract `failure_report.py`. Validation: full tests.

## Tradeoffs

- **Pro**: Two PRs, minimal risk, two tight single-purpose modules
  that would exist in every variant of this refactor anyway. Good
  first step regardless of end state.
- **Pro**: The extracted surfaces are pure enough to earn
  property-based tests (status-block parser round-trips, YAML scalar
  escaping). Matches taste's test-shape guidance.
- **Con**: `loop.py` remains large. Routing + run orchestration still
  tangled. Leaves the main readability problem unsolved — the file
  still mixes "what should this attempt do next" with "how do we run
  a whole refactoring session."
- **Con**: Risks a local optimum. If the larger split is the right
  destination, this phase is useful prep, not a stopping point.

## Risk Profile

Very low. Both extractions are mechanical moves of self-contained code.
Best viewed as Phase 1–2 of `split-by-domain` rather than a terminal
plan. Recommended only if time/review budget forces stopping short.
