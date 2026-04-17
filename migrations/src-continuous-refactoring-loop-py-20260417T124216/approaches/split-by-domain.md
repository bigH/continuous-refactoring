# Approach: Split loop.py by Domain

## Summary

`loop.py` is 1656 lines carrying four distinct domains glued together:
status parsing, failure reporting, routing/dispatch, and run orchestration.
Extract each into its own module so `loop.py` is left with the two public
entrypoints (`run_once`, `run_loop`) and thin orchestration glue.

## Target Shape

- `decisions.py` — `AgentStatus`, `DecisionRecord`, `RunnerDecision`,
  `RetryRecommendation`, `RouteOutcome`, the status-block parser, and the
  small text-sanitation helpers (`_sanitize_text`, `_status_summary`,
  `_resolved_phase_reached`, `_error_failure_kind`, `_default_retry_recommendation`).
- `failure_report.py` — `_write_reason_for_failure`, `_next_step_text`,
  `_yaml_scalar`, `_persist_decision`, `_effective_record`,
  `_relative_path`. Owns the reason-for-failure document format end-to-end.
- `routing.py` already exists (classifier); add a sibling `routing_pipeline.py`
  (or fold into `routing.py` if it stays coherent) for `_try_migration_tick`,
  `_enumerate_eligible_manifests`, `_expand_target_for_classification`,
  `_route_and_run`, `_scope_bypass_context`, `RouteResult`,
  `_describe_planning_outcome`, `_migration_name_from_target`.
- `loop.py` keeps `run_once`, `run_loop`, `run_baseline_checks`,
  `_run_refactor_attempt`, `_finalize_commit`, the arg helpers
  (`_resolve_*`, `_parse_paths_arg`, `_build_target_fallback`,
  `_effective_max_attempts`, `_sleep_between_targets`), and `_retry_context`.

Target: `loop.py` around 500 lines, each new module 200–400 lines.

## Phases

1. **Extract decisions** — move status/decision types + parsing + sanitizers.
   Pure functions, no side effects. Validation: `pytest` green.
2. **Extract failure_report** — move reason-doc writing and `_persist_decision`.
   Touches `artifacts` + filesystem; imports `decisions`. Validation: green.
3. **Extract routing_pipeline** — move routing, migration tick, scope
   expansion wiring. Imports `decisions` + `failure_report`. Validation: green.
4. **Trim loop.py** — delete re-exports, tighten imports, confirm
   `run_once`/`run_loop` read cleanly top-to-bottom.

Each phase is one commit, its own PR.

## Tradeoffs

- **Pro**: Aligns with taste — domain-focused modules, meaningful FQNs
  (`decisions.AgentStatus`, `failure_report.write`), no speculative classes.
  Biggest readability win per unit of risk. Each new module has a real,
  distinct reason to exist.
- **Pro**: Shrinks `loop.py`'s cognitive surface ~3x; future changes to
  failure-doc format or routing no longer churn the orchestrator file.
- **Con**: 3 new import sites and some churn in tests that reach into
  private helpers. Mitigated — tests mostly exercise public entrypoints.
- **Con**: `routing.py` already names the classifier; adding a pipeline
  module next to it risks mild naming overlap. Resolve by either merging
  (one `routing.py`) or using `routing/` package if size warrants.

## Risk Profile

Low-to-moderate. All moves are mechanical; the logic inside each function
is unchanged. Wide-blast-radius is limited to imports — validation is the
existing test suite plus a `run-once` smoke run. No flags, no staged
rollout (per taste): do it directly on the branch.
