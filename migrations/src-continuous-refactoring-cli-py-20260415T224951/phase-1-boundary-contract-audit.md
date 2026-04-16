# Phase 1: boundary-contract-audit

## Objective

Build a mechanically checkable boundary contract inventory before any behavior changes.

## Scope

- `src/continuous_refactoring/agent.py`
- `src/continuous_refactoring/prompts.py`
- `src/continuous_refactoring/config.py`
- `src/continuous_refactoring/loop.py`
- `src/continuous_refactoring/artifacts.py`
- `src/continuous_refactoring/__init__.py`
- `src/continuous_refactoring/__main__.py`
- `src/continuous_refactoring/cli.py`

No source code edits in this phase.

## Hard artifact to create

Create `phase-1-boundary-contract-audit-notes.json` in this migration directory.

Required schema per entry:

```json
{
  "edge_id": "string",
  "source_module": "string",
  "source_symbol": "string",
  "caught_in_module": "string",
  "caught_symbol": "string",
  "raised_type": "string",
  "raised_message": "string",
  "is_wrapped": true,
  "cause_preserved": true,
  "owner_boundary": "agent|config|loop|cli|artifacts|__init__|__main__",
  "notes": "string"
}
```

`is_wrapped` must be `true` when the catch site is expected to produce a boundary wrap.  
`cause_preserved` must be `true` whenever `is_wrapped` is `true`.

## Instructions

1. Extract all exception-handling sites from each scoped module.
2. Classify each boundary edge into:
   1. boundary-owned and already causal,
   2. boundary-owned and currently missing causal chain,
   3. mid-stack translation that should be re-homed.
3. Resolve each edge owner using one of:
   - `agent`
   - `config`
   - `loop`
   - `cli`
   - `artifacts`
   - `__init__`
   - `__main__`
4. Record every decision in `phase-1-boundary-contract-audit-notes.json` using only module-level ownership for each edge.
5. Keep this phase file list as read-only until phase 2 to guarantee a clean audit baseline.

## Ready_when (mechanical)

1. `phase-1-boundary-contract-audit-notes.json` exists.
2. JSON parses with `jq` and has no empty `owner_boundary`.
3. Every entry has all required keys and boolean values for `is_wrapped` and `cause_preserved`.
4. `rg -n "raise |except" src/continuous_refactoring/{agent.py,prompts.py,config.py,loop.py,artifacts.py,__init__.py,__main__.py,cli.py}` shows no edits after audit start (plan requires phase-1 is read-only).

## Validation

1. Confirm no file mutations outside this migration directory and this phase file.
2. Confirm the notes artifact has at least one entry for each raised exception site in scope.
3. Confirm each non-boundary edge has explicit owner and no duplicate `edge_id`.

