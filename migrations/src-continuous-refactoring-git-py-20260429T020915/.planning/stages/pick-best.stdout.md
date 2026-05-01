# Reconstructed Planning Step: pick-best

Chosen approach: `inplace-domain-seams`.

Reasoning:
- It keeps `src/continuous_refactoring/git.py` as the stable git boundary.
- It has the lowest blast radius for `loop.py`, `refactor_attempts.py`,
  `phases.py`, `migration_tick.py`, `routing_pipeline.py`, and package-root
  exports.
- The main risk is behavioral drift, so characterization tests should precede
  structural cleanup.
- Module extraction remains a runner-up, but it is more churn than this target
  needs before the current behavior is locked down.

