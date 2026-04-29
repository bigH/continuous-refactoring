taste-scoping-version: 1

- Do translate and wrap errors at module boundaries using exception nesting. Avoid translating inside a module when bubbling preserves signal.
- Do keep comments near zero. Avoid comments when clearer code carries intent.
- Do allow small abstractions when they improve readability, flow, or repetition. Avoid layers that hide behavior without clarity gains.
- Do aggressively delete legacy/fallback code in non-shipped projects. Avoid keeping dead flags, tables, or shims once unused.
- Do choose safer compatibility paths for shipped systems. Avoid risky hard cuts until rollout risk is acceptable.
- Do treat released package interfaces as human-review territory: CLI behavior, XDG state, repo-written files, migration manifest structure, and other system interactions. Avoid changing those contracts without clearly surfacing the behavior change for review.
- Do make human-review prompts name the interface behavior change when interface risk is the reason for review. Avoid generic "needs review" language that hides what users or local installs will experience.
- Do roll out wide-blast-radius changes directly in this project, while keeping taste versioning and live migrations correct. Avoid flag/canary patterns that conflict with versioned migration behavior.
- Do use truthful rollout names (`canary`, `upgraded`, `versionBeingRolledOut`) for transitional state. Avoid weak names like `new`, `v2`, or `temp` for long-lived concepts.
- Do use `temp` only when lifecycle is truly temporary. Avoid using `temp` for ordinary local variables just because scope is short.
- Do keep module boundaries domain-focused and FQNs meaningful. Avoid mechanical module reshaping or overuse of `__init__.py`.
- Do shape large-scope structure around sensible module size and callsite usage so imports/FQNs are helpful without verbosity. Avoid split/unify decisions detached from real usage.
- Do introduce interfaces when there is more than one implementation, or clear intent for more than one soon. Avoid speculative interfaces for single concrete behavior.
- Do choose tests by code shape: property-based for pure, fast, bounded functions; example-based for integration-heavy behavior. Avoid tests that assert calls instead of outcomes.
- Do prefer real collaborators in tests where feasible. Avoid mocks unless boundary isolation is genuinely necessary.
