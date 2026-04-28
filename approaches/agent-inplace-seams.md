# Approach: In-Place Seams Inside `agent.py`

## Strategy
- Keep `src/continuous_refactoring/agent.py` as one module for now.
- Refactor internally around three truthful sections:
  - command construction and backend validation,
  - interactive settle lifecycle and terminal recovery,
  - observed command execution and watchdog logging.
- Normalize helper naming and data flow so the public API reads top-down without changing imports anywhere else.
- Add a small amount of typed structure only where it shortens branches or clarifies return values.

## Tradeoffs
- Safest path. No import churn, no package-surface changes, minimal merge pain.
- Best fit if the immediate problem is readability and local change friction, not module count.
- Leaves `agent.py` large. It gets cleaner, but not smaller in a meaningful architectural way.
- Does not create future domain boundaries for backend-specific behavior.

## Estimated phases
1. Reorder and tighten private helpers so command-building, settle logic, and observed-command logic read as coherent blocks.
   - `required_effort`: `low`
2. Introduce small internal value helpers where they remove repetitive branching without hiding behavior.
   - `required_effort`: `low`
3. Update tests to reflect any renamed helpers or changed internal flow, while keeping behavior identical.
   - `required_effort`: `low`
4. Run full pytest and remove dead local helper paths uncovered during the cleanup.
   - `required_effort`: `low`

## Risk profile
- Technical risk: low
- Blast radius: low
- Failure modes:
  - Accidental behavior drift in settle timing or Claude output extraction during local cleanup.
  - Over-tidying that obscures the load-bearing Codex terminal reset and watchdog semantics.

## Best when
- We want the fastest safe readability win.
- We do not yet know which future split is actually worth carrying.
