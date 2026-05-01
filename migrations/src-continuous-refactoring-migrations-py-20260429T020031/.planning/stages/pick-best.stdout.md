# Reconstructed Planning Step: pick-best

Chosen approach: `manifest-ops-module-split`.

Reasoning:
- It moves operational manifest logic out of `migrations.py` without changing
  the public manifest facade.
- It fits the existing `migration_manifest_codec.py` boundary instead of
  forcing a bigger architecture split.
- It gives later phases a focused internal module while preserving compatibility
  exports through `continuous_refactoring.migrations`.
- The pure-kernel split is cleaner in theory but too much churn for this
  migration without first locking behavior.

