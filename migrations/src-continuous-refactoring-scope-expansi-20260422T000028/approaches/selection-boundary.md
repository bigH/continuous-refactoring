# Selection Boundary Extraction

## Strategy

Separate the agent-facing selection boundary from candidate generation.

Keep `scope_expansion.py` as the owner of candidate discovery and bypass logic. Move selection-agent concerns into a new module, likely `src/continuous_refactoring/scope_selection.py`:

- `ScopeSelection`
- `parse_scope_selection`
- `select_scope_candidate`
- selection stdout/last-message artifact paths
- calls to `maybe_run_agent`

Then `scope_expansion.py` can focus on building candidates and translating a selected candidate into the expanded `Target`. `routing_pipeline.py` can either continue calling the combined expansion API or import selection pieces directly if that reads better.

## Tradeoffs

Pros:
- Extracts the strongest boundary: external agent execution and output parsing.
- Keeps pure discovery imports stable if desired.
- Error translation remains at a real boundary: failed selection-agent runs become `ContinuousRefactorError`.
- Parser tests already exist and can move cleanly.

Cons:
- Leaves the large candidate-discovery block in `scope_expansion.py`.
- Adds a module for a relatively small amount of code.
- `prompts.py` still needs candidate formatting, so type ownership may remain awkward unless carefully scoped.
- The name `scope_selection.py` could be confused with existing `tests/test_scope_selection.py`, though that is probably fine.

## Estimated Phases

1. **Pin selection boundary behavior**
   - Move or strengthen parser tests around valid lines, malformed output, empty output, and unavailable candidate kinds.
   - Add a narrow test for single-candidate selection writing both selection artifacts if not already covered elsewhere.

2. **Extract selection module**
   - Move `ScopeSelection`, `_SELECTION_RE`, `parse_scope_selection()`, and `select_scope_candidate()`.
   - Update imports in tests and any source call sites.
   - Keep exception wrapping at the selection boundary and preserve causes if new wrapping is introduced.

3. **Clean artifact flow**
   - Decide whether `write_scope_expansion_artifacts()` stays in `scope_expansion.py` or moves with selection artifacts.
   - Prefer keeping JSON variant writing in `scope_expansion.py` unless selection artifacts become a tiny cohesive helper.

4. **Validation**
   - Run `uv run pytest tests/test_scope_selection.py tests/test_scope_expansion.py tests/test_scope_loop_integration.py tests/test_prompts_scope_selection.py`.
   - Run `uv run pytest`.

## Risk Profile

Medium-low risk. Agent execution is a boundary with obvious tests, and candidate scoring remains mostly untouched.

Main watch-outs:
- Do not translate parse errors twice. `parse_scope_selection()` already raises `ContinuousRefactorError` with useful messages.
- Preserve the exact output contract line accepted by recorded Claude fixture tests.
- Keep selection artifact filenames stable: `selection.stdout.log`, `selection.stderr.log`, and `selection-last-message.md`.

## Best Fit

Choose this if the team wants better boundary clarity without touching candidate scoring. It improves error locality and test shape, but it does less for the densest part of the module.
