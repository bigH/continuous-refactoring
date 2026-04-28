# Parser And Discovery Split

## Strategy
Refactor `planning.py` into a thinner orchestrator by extracting two cohesive responsibilities:

- planning output parsing and review interpretation
- phase file discovery and metadata extraction

The orchestrator then reads like a workflow, while parsing and filesystem-derived phase metadata live behind narrow helpers or a dedicated module if the resulting FQNs stay honest.

## Why It Fits The Taste
- Splits by real responsibility, not by arbitrary size.
- Keeps comments near zero by making the code tell the story.
- Improves test shape: pure parsing code can get tighter, table-driven coverage.
- Avoids speculative interfaces because each extraction has a single concrete purpose.

## Likely Changes
- Extract decision parsing, review finding detection, and section parsing into a focused helper area.
- Extract phase markdown discovery into a separate helper/module that owns `Precondition` and optional effort metadata parsing.
- Leave agent execution, manifest writes, and planning stage order in `planning.py`.
- Rework tests so pure parsing/discovery behavior is verified separately from workflow behavior.

## Tradeoffs
- Pro: Stronger separation between pure logic and side-effect orchestration.
- Pro: Makes future changes to phase metadata rules safer.
- Pro: Better long-term readability than a pipeline-only cleanup.
- Con: Slightly larger module-boundary change.
- Con: Risks ending up with a helper module that is too anemic if extraction is not disciplined.
- Con: Requires touching `__init__.py` only if a new public export accidentally leaks, which should be avoided.

## Estimated Phases
1. `low` — Add characterization tests around parser/discovery edge cases and current error behavior.
2. `medium` — Extract pure parsing/discovery helpers and rewire `planning.py` to use them.
3. `low` — Delete obsolete locals, tighten names, and ensure internal modules stay internal.

## Risk Profile
- Delivery risk: low-medium
- Regression risk: medium
- Design payoff: medium-high
- Best when: the real pain is mixed concerns inside `planning.py`, not just repetitive flow

## Failure Modes To Watch
- Creating a module split that makes imports less meaningful than the status quo.
- Translating errors too early and losing useful parsing/file context.
- Letting tests overfit helper internals instead of protecting behavior.
