from __future__ import annotations

from types import ModuleType

from continuous_refactoring import agent
from continuous_refactoring import artifacts
from continuous_refactoring import cli
from continuous_refactoring import decisions
from continuous_refactoring import failure_report
from continuous_refactoring import git
from continuous_refactoring import loop
from continuous_refactoring import migration_tick
from continuous_refactoring import migrations
from continuous_refactoring import phases
from continuous_refactoring import planning
from continuous_refactoring import prompts
from continuous_refactoring import routing
from continuous_refactoring import routing_pipeline
from continuous_refactoring import scope_candidates
from continuous_refactoring import scope_expansion

_SUBMODULES: tuple[ModuleType, ...] = (
    agent,
    artifacts,
    cli,
    decisions,
    failure_report,
    git,
    loop,
    migration_tick,
    migrations,
    phases,
    planning,
    prompts,
    routing,
    routing_pipeline,
    scope_candidates,
    scope_expansion,
)


def _reexport() -> tuple[str, ...]:
    exports: list[str] = []
    for module in _SUBMODULES:
        for name in module.__all__:
            if name in exports:
                raise RuntimeError(
                    f"Duplicate exported symbol in package __init__: {name!r}"
                )
            globals()[name] = getattr(module, name)
            exports.append(name)
    return tuple(exports)


__all__: tuple[str, ...] = _reexport()
