# Stage Pipeline Tightening

## Strategy
Keep `planning.py` as the orchestration module, but make the stage flow explicit and less repetitive. Collapse the repeated "run stage, rebuild context, touch manifest" pattern into a small pipeline structure with stage-specific inputs. Keep parsing and phase discovery local unless a clean boundary falls out naturally.

This is the lowest-risk path because it preserves the current module shape, prompt API, and manifest behavior while reducing the copy-paste control flow that currently spreads stage semantics across `run_planning()`.

## Why It Fits The Taste
- Keeps the boundary domain-focused: `planning.py` still owns planning orchestration.
- Adds abstraction only where the current repetition hurts readability.
- Avoids speculative interfaces and avoids mechanical module churn.
- Preserves boundary error translation at real filesystem/agent boundaries.

## Likely Changes
- Introduce a small stage spec/value object for label, prompt stage, and context builder.
- Move stage sequencing into a data-driven loop for the always-run stages.
- Keep the revise/review-2 branch explicit, since it is genuinely different.
- Tighten helper naming around context assembly and manifest refresh.
- Expand tests around stage order, prompt inputs, and manifest refresh after phase file changes.

## Tradeoffs
- Pro: Best clarity-to-risk ratio.
- Pro: Minimal blast radius across prompts/tests.
- Pro: Easy to verify with existing example-style tests.
- Con: Leaves parsing, phase discovery, and manifest sync concerns in one module.
- Con: Some repetition will remain because the revise branch should probably stay special.

## Estimated Phases
1. `low` — Add characterization tests for stage sequencing, context reloading, and manifest refresh points.
2. `medium` — Refactor `run_planning()` into an explicit stage pipeline while preserving behavior.
3. `low` — Tighten helper names and delete now-dead helpers or duplicated branches.

## Risk Profile
- Delivery risk: low
- Regression risk: low
- Design payoff: medium
- Best when: the goal is a safer readability refactor, not a larger responsibility split

## Failure Modes To Watch
- Accidentally changing which manifest touches happen before or after each stage.
- Reusing stale `plan.md` or approach content in follow-up review stages.
- Over-generalizing the revise path and hiding important behavior.
