# Scheduling Boundary

## Strategy

Extract wake-up and cooldown logic from `migrations.py` into a focused scheduling module, likely `src/continuous_refactoring/migration_schedule.py`.

Move or consolidate:
- `eligible_now()`
- `bump_last_touch()`
- `_COOLDOWN`
- `_STALE`
- possibly `_defer_manifest()` from `migration_tick.py`

The target shape is a small concrete scheduling boundary:
- `is_migration_eligible(manifest, now)`
- `touch_manifest(manifest, now)`
- `defer_manifest(manifest, now, verdict, reason)`

This would put the “when should the driver reconsider this migration?” rules in one place, instead of splitting eligibility in `migrations.py` and deferral mutation in `migration_tick.py`.

## Tradeoffs

Pros:
- Names the retry-gate behavior that `AGENTS.md` calls load-bearing.
- Pulls cooldown/wake-up policy closer to the code that mutates those fields.
- Makes `migration_tick.py` read more like orchestration and less like state policy.
- Focused tests in `tests/test_wake_up.py` can become scheduling tests with real manifest values.

Cons:
- Does not address the noisy manifest JSON parser in `migrations.py`.
- `eligible_now()` and `bump_last_touch()` are small today; extracting only them may be too thin.
- Moving `_defer_manifest()` touches `migration_tick.py` and related focused-loop tests.
- The schedule module can become a bucket if it starts absorbing unrelated manifest mutations.

## Estimated Phases

1. **Pin scheduling semantics**
   - Strengthen tests around cooldown priority over stale wake-up, unverifiable review flags, and successful phase completion clearing cooldown.
   - Keep assertions on manifest fields, not helper call paths.

2. **Extract eligibility and touch**
   - Create `migration_schedule.py`.
   - Move `eligible_now()` and `bump_last_touch()` with names that describe scheduling, not generic mutation.
   - Update imports in `migration_tick.py`, `tests/test_wake_up.py`, and package exports if the functions remain public.

3. **Move deferral policy**
   - Move `_defer_manifest()` from `migration_tick.py` if the extraction still feels cohesive.
   - Keep route-record creation in `migration_tick.py`; scheduling should not know about decisions or artifacts.

4. **Clean migration domain module**
   - Remove stale comments and dead constants from `migrations.py`.
   - Run `uv run pytest tests/test_wake_up.py tests/test_loop_migration_tick.py tests/test_focus_on_live_migrations.py`, then `uv run pytest`.

## Risk Profile

Medium-low. The policy is important, but it is narrow and already has direct tests.

Main watch-outs:
- Preserve the current priority: active `cooldown_until` blocks eligibility even when `wake_up_on` is in the past.
- Preserve the 7-day stale fallback.
- Do not let scheduling code import `migration_tick.py` or decision types.
- Update `AGENTS.md` if the documented migration scheduling split changes.

## Best Fit

Choose this if the immediate pain is the cooldown/wake-up behavior rather than file size. It is not the strongest standalone cleanup for `migrations.py`, but it protects a subtle policy before larger reshaping.
